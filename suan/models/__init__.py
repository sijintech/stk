"""Model gateway of this computer (docs/design/model-gateway.md): model endpoints, their keys, the network
setting and the data boundary checked before a request is sent."""
from .gateway import ModelGateway, OpenAICompatibleAdapter, PolicyDenied
from .local import LocalModels
from .settings import ADAPTER_PREFIX, BUILTIN_ID, LOCATIONS, NETWORK_MODES, EndpointKeys, Endpoints, ModelPolicy

__all__ = ["ADAPTER_PREFIX", "BUILTIN_ID", "LOCATIONS", "NETWORK_MODES", "EndpointKeys", "Endpoints", "LocalModels", "ModelGateway",
           "ModelPolicy", "OpenAICompatibleAdapter", "PolicyDenied"]
