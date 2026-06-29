"""Testes básicos para langchat_open."""

import importlib


def test_app_imports():
    """Verifica que os módulos principais são importáveis."""
    modulos = ["app.config"]
    for modulo in modulos:
        importlib.import_module(modulo)


def test_config_tem_chaves():
    """Verifica que o módulo de config expõe as variáveis esperadas."""
    from app import config

    assert hasattr(config, "OPENAI_API_KEY") or hasattr(config, "ANTHROPIC_API_KEY") or hasattr(config, "LLM_PROVIDER")
