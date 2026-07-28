import os

# `Settings` (grc/sinc_amn/config.py) exige estas variables sin valor por
# defecto y se instancia a nivel de modulo en los clients (Auron/Maisa/Noxus)
# y en db/pool.py, asi que deben existir antes de importar `sinc_amn.main`
# en cualquier test.
os.environ.setdefault("SINC_AMN_AURON_BASE_URL", "https://auron.test")
os.environ.setdefault("SINC_AMN_AURON_API_KEY", "test-auron-api-key")
os.environ.setdefault("SINC_AMN_AURON_ZEN_INSTANCE_ID", "test-zen-instance")
os.environ.setdefault("SINC_AMN_MAISA_BASE_URL", "https://maisa.test")
os.environ.setdefault("SINC_AMN_MAISA_API_KEY", "test-maisa-api-key")
os.environ.setdefault("SINC_AMN_NOXUS_BASE_URL", "https://noxus.test")
os.environ.setdefault("SINC_AMN_NOXUS_API_KEY", "test-noxus-api-key")
os.environ.setdefault("SINC_AMN_GENERIC_USE_CASE_ID", "test-generic-use-case")
os.environ.setdefault(
    "SINC_AMN_INTERMEDIATE_DB_DSN", "postgresql://test:test@localhost/test"
)
os.environ.setdefault("SINC_AMN_MAISA_ORGANIZATION_ID", "test-org")
