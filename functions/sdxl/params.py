from params import RequestData, ControlNet_RequestData, IPAdapter_RequestData
from typing import Optional, Literal, List


class SDXL_RequestData(RequestData):
    basemodel: str
    steps: int = 20
    cfg: float = 7
    sampler_name: str = 'dpmpp_2m_sde'
    scheduler: str = 'karras'
    init_image: Optional[str]= None
    mask: Optional[str]= None
    controlnet_requests: Optional[List[ControlNet_RequestData]] = []
    ipadapter_request: Optional[IPAdapter_RequestData] = None
    gen_type: Literal['t2i', 'i2i', 'inpaint'] = 't2i'
    refiner: Optional[str] = None
    refine_switch: float= 0.4