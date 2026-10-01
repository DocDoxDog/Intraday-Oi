"""Import smoke tests for the production package execution path."""


def test_production_module_imports():
    import src.main  # noqa: F401
    import src.url_manager  # noqa: F401
    import src.parser  # noqa: F401
    import src.llm_gateway  # noqa: F401
    import src.local_supabot  # noqa: F401
    import src.supabot_llm  # noqa: F401
