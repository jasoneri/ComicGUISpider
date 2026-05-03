class EhResp:
    _case_map = {
        "This IP address has been temporarily banned due to an excessive request rate":
            "Your IP address has been blocked by eh.<br> Please change your proxy node.",
    }

    @classmethod
    def catch(cls, text):
        for raw, message in cls._case_map.items():
            if raw in text:
                raise ValueError(message)
