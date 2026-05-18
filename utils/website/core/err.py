class SiteBusinessError(ValueError):
    """Expected site/business-level exception shown to the operator."""


class EhResp:
    _case_map = {
        "This IP address has been temporarily banned due to an excessive request rate":
            "Your IP address has been blocked by eh.<br> Please change your proxy node.",
    }

    @classmethod
    def catch(cls, text):
        for raw, message in cls._case_map.items():
            if raw in text:
                raise SiteBusinessError(message)


class Dm5Resp:
    _case_map = {
        "动漫屋已不再提供": "dm5 不提供此漫画阅读",
    }

    @classmethod
    def catch(cls, text):
        for raw, message in cls._case_map.items():
            if raw in text:
                raise SiteBusinessError(message)
