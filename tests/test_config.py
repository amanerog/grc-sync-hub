from sinc_amn.config import Settings


def test_auron_base_url_defaults_from_zen_instance_id():
    settings = Settings(
        auron_base_url=None,
        auron_zen_instance_id="94a9c3fd-21af-4f38-80d5-a059ddf0bc46",
    )

    assert settings.auron_base_url == (
        "https://94a9c3fd-21af-4f38-80d5-a059ddf0bc46.eu-de.openpages.cloud.ibm.com"
    )


def test_auron_base_url_explicit_value_is_not_overridden():
    settings = Settings(
        auron_base_url="https://custom-host.example.com",
        auron_zen_instance_id="94a9c3fd-21af-4f38-80d5-a059ddf0bc46",
    )

    assert settings.auron_base_url == "https://custom-host.example.com"
