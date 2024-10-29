import torch
from .utils import (model_patch,
                    construct_controlnet_condition,
                    construct_ipadapter_condition,
                    detailer,
                    construct_hand_detailer_condition,
                    pad_image_to_aspect_ratio)
from cgen_utils.image_process import convert_image_tensor_to_base64, convert_base64_to_image_tensor
from cgen_utils.comfyui import (encode_prompt,
                                sample_image,
                                decode_latent,
                                encode_image,
                                )
from functions.gemini.utils import send_gemini_request_to_api
import random

@torch.inference_mode()
def generate_image(cached_model_dict, request_data):
    unet_base = cached_model_dict['unet']['sd15']['base'][1]
    vae_base = cached_model_dict['vae']['sd15']['base'][1]
    clip_base = cached_model_dict['clip']['sd15']['base'][1]

    unet_refine = cached_model_dict['unet']['sd15']['refiner'][1]
    vae_refine = cached_model_dict['vae']['sd15']['refiner'][1]
    clip_refine = cached_model_dict['clip']['sd15']['refiner'][1]

    is_animation_style = len(request_data.controlnet_requests) == 2

    start_base = 10 if is_animation_style else 12
    end_base = 20
    start_refine = end_base
    end_refine = request_data.steps

    cfg_base = 4 if is_animation_style else 2
    cfg_refine = 7 if is_animation_style else 8

    init_image = convert_base64_to_image_tensor(request_data.init_image) / 255
    init_noise = encode_image(vae_refine if is_animation_style else vae_base, init_image)

    if is_animation_style:
        unet_base = model_patch(unet_base)

    ipadapter_request = request_data.ipadapter_request
    controlnet_requests = request_data.controlnet_requests

    seed = random.randint(1, int(1e9)) if request_data.seed == -1 else request_data.seed

    prompt_positive_prefix = 'Modisn disney, pixar 3d animation style image.\n'
    prompt_positive_base = prompt_positive_prefix +  send_gemini_request_to_api(query_type='i2c_description', image=init_image * 255)

    prompt_positive_refine = prompt_positive_base if is_animation_style else 'best quality,masterpiece,'
    prompt_negative = request_data.prompt_negative


    unet_base = construct_ipadapter_condition(
        unet_base,
        cached_model_dict,
        ipadapter_request
    )

    # Base Model Flow
    positive_cond, negative_cond = encode_prompt(clip_base,
                                                 prompt_positive_base,
                                                 prompt_negative)

    positive_cond_base, negative_cond_base = construct_controlnet_condition(
        cached_model_dict,
        positive_cond,
        negative_cond,
        controlnet_requests,
    )

    latent_image = sample_image(
        unet= unet_base,
        positive_cond= positive_cond_base,
        negative_cond= negative_cond_base,
        latent_image= init_noise,
        seed= seed,
        steps= request_data.steps,
        cfg= cfg_base,
        sampler_name= request_data.sampler_name,
        scheduler= request_data.scheduler,
        start_at_step= start_base,
        end_at_step= end_base,
        add_noise = 'enable',
        return_with_leftover_noise='enable'
    )

    positive_cond_refine, negative_cond_refine = encode_prompt(
        clip_refine,
        prompt_positive_refine,
        prompt_negative
    )

    seed = random.randint(1, int(1e9)) if request_data.seed == -1 else request_data.seed

    latent_image = sample_image(
        unet=unet_refine,
        positive_cond=positive_cond_refine,
        negative_cond=negative_cond_refine,
        latent_image=latent_image,
        seed=seed,
        steps=request_data.steps,
        cfg=cfg_refine,
        sampler_name=request_data.sampler_name,
        scheduler=request_data.scheduler,
        start_at_step=start_refine,
        end_at_step=end_refine,
        add_noise='disable',
        return_with_leftover_noise='disable'
    )

    image_tensor = decode_latent(vae_refine if is_animation_style else vae_base, latent_image)

    seed = random.randint(1, int(1e9)) if request_data.seed == -1 else request_data.seed

    face_prompt = prompt_positive_prefix + 'Detailed Face, eye, nose, lips.'
    # Base Model Flow
    positive_face, negative_face = encode_prompt(clip_base,
                                                 face_prompt,
                                                 prompt_negative)

    image_face_detailed_tensor = detailer(
        image_tensor,
        unet_refine if is_animation_style else unet_base,
        clip_refine,
        vae_refine,
        positive_face,
        negative_face,
        seed
    )


    # Add Hand detailer
    positive_cond, negative_cond = construct_hand_detailer_condition(
        init_image,
        positive_cond,
        negative_cond
    )

    image_tensor = detailer(
        image_tensor,
        unet_refine if is_animation_style else unet_base,
        clip_refine,
        vae_refine,
        positive_cond,
        negative_cond,
        seed,
        bbox_detector_name = 'bbox/hand_yolov8s.pt',
        bbox_threshold = 0.5,
        wildcard_opt= 'perfect hand,fine fingers'
    )
    image_face_detailed_tensor = detailer(
        image_face_detailed_tensor,
        unet_refine if is_animation_style else unet_base,
        clip_refine,
        vae_refine,
        positive_cond,
        negative_cond,
        seed,
        bbox_detector_name='bbox/hand_yolov8s.pt',
        bbox_threshold=0.5,
        wildcard_opt='perfect hand,fine fingers'
    )

    image_tensor_print = pad_image_to_aspect_ratio(image_tensor.squeeze())
    image_face_detailed_tensor_print = pad_image_to_aspect_ratio(image_face_detailed_tensor.squeeze())

    image_base64 = convert_image_tensor_to_base64(image_tensor * 255)
    image_base64_print = convert_image_tensor_to_base64(image_tensor_print * 255)
    image_face_detailed_base64 = convert_image_tensor_to_base64(image_face_detailed_tensor * 255)
    image_face_detailed_base64_print = convert_image_tensor_to_base64(image_face_detailed_tensor_print * 255)
    # Image resize H:W = 3:2

    return image_base64, image_base64_print, image_face_detailed_base64, image_face_detailed_base64_print
