import torch
from .utils import webui_lama_proprecessor, construct_condition
from functions.gemini.utils import send_gemini_request_to_api
from cgen_utils.image_process import convert_image_tensor_to_base64, convert_base64_to_image_tensor, convert_image_array_to_base64
from cgen_utils.comfyui import (encode_prompt,
                                sample_image,
                                decode_latent,
                                encode_image,
                                encode_image_for_inpaint,
                                mask_blur)
import random


@torch.inference_mode()
def remove(cached_model_dict, request_data):
    unet = cached_model_dict['unet']['sdxl']['base'][1]
    vae = cached_model_dict['vae']['sdxl']['base'][1]
    clip = cached_model_dict['clip']['sdxl']['base'][1]

    start_base = int(request_data.steps - request_data.steps * request_data.denoise)
    end_base = request_data.steps

    init_image = convert_base64_to_image_tensor(request_data.init_image) / 255
    mask = convert_base64_to_image_tensor(request_data.mask) / 255
    mask = mask_blur(mask)
    lama_preprocessed = webui_lama_proprecessor(init_image, mask).unsqueeze(0) / 255
    # Gemini prompt
    prompt = send_gemini_request_to_api(query_type='image_description', image=lama_preprocessed * 255)
    print('Object Removal Prompt:', prompt)
    seed = random.randint(1, int(1e9)) if request_data.seed == -1 else request_data.seed
    positive_cond, negative_cond = encode_prompt(clip,
                                                 prompt,
                                                 request_data.prompt_negative)
    unet = construct_condition(
        unet,
        vae,
        lama_preprocessed,
        mask,
        request_data.inpaint_model_name
    )

    init_noise = encode_image_for_inpaint(vae, init_image, mask, grow_mask_by=6)

    latent_image = sample_image(
        unet=unet,
        positive_cond=positive_cond,
        negative_cond=negative_cond,
        latent_image=init_noise,
        seed=seed,
        steps=request_data.steps,
        cfg=request_data.cfg,
        sampler_name=request_data.sampler_name,
        scheduler=request_data.scheduler,
        start_at_step=start_base,
        end_at_step=end_base, )

    image_tensor = decode_latent(vae, latent_image)
    image_tensor = image_tensor * mask.unsqueeze(-1) + init_image * (1 - mask.unsqueeze(-1))
    image_base64 = convert_image_tensor_to_base64(image_tensor * 255)

    return image_base64
