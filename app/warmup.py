"""
Pré-aquecimento do cache semântico.

Duas estratégias:
- seed_demo_cache: injeta Q&A fixos para o banco demo (sem chamar o agente)
- warmup_agent:    roda perguntas reais em background para qualquer banco
"""
import logging
import uuid

logger = logging.getLogger(__name__)

_CLIENTES_RESP = (
    "Temos 8 clientes cadastrados. Destes, 6 estão ativos e 2 inativos (Diego Rocha e Hugo Nunes). "
    "Os clientes Enterprise (Carla Mendes e Gabi Lima) representam a maior receita individual — "
    "vale investir em retenção e upsell nesse segmento."
)
_PRODUTOS_RESP = (
    "Temos 8 produtos no catálogo, distribuídos em 3 categorias: Periféricos (5), Eletrônicos (2) e Armazenamento (1). "
    "O produto com maior estoque é o Hub USB-C (200 unidades) e o de menor estoque é o Notebook Ultra (23 unidades)."
)
_PEDIDOS_RESP = (
    "Temos 10 pedidos registrados no sistema. O cliente com mais pedidos é Ana Silva (3 pedidos), "
    "seguida por Carla Mendes e Gabi Lima (2 pedidos cada). "
    "Concentrar ações de fidelização nos top clientes pode aumentar o ticket médio."
)
_PRODUTO_TOP_RESP = (
    "O Notebook Ultra é o produto de maior valor vendido (2 × R$ 4.599,90 = R$ 9.199,80). "
    "Em volume, o Hub USB-C lidera com 5 unidades em um único pedido. "
    "Considere criar bundles de Notebook Ultra + periféricos para aumentar o ticket médio."
)
_RECEITA_RESP = (
    "A receita total dos pedidos é de aproximadamente R$ 20.148,40. "
    "Os maiores contribuidores são Carla Mendes (R$ 5.399,70) e Gabi Lima (R$ 5.449,40). "
    "O segmento Enterprise responde por mais de 50% da receita — priorize a retenção desses clientes."
)
_INATIVOS_RESP = (
    "Há 2 clientes inativos: Diego Rocha (Belo Horizonte, plano Starter) e Hugo Nunes (Fortaleza, plano Starter). "
    "Uma campanha de reativação com desconto de upgrade para Pro pode ser eficaz."
)
_MRR_RESP = (
    "Os clientes com maior receita mensal são Carla Mendes e Gabi Lima (plano Enterprise, R$ 999,90/mês cada). "
    "Em seguida, Ana Silva, Elena Ferreira e Felipe Santos (plano Pro, R$ 299,90/mês). "
    "O MRR total é de R$ 3.898,10."
)
_PLANOS_RESP = (
    "Existem 3 planos: Starter (R$ 99,90/mês) com 3 clientes, Pro (R$ 299,90/mês) com 3 clientes, "
    "e Enterprise (R$ 999,90/mês) com 2 clientes. "
    "O plano Pro tem a melhor relação volume × receita."
)
_CAROS_RESP = (
    "Os 3 produtos mais caros: Notebook Ultra (R$ 4.599,90), Monitor 4K (R$ 2.399,90) e Headset Gamer (R$ 599,90). "
    "Considere garantia estendida como upsell nesses itens de alto valor."
)
_CIDADES_RESP = (
    "A base está distribuída em 8 cidades: São Paulo, Rio de Janeiro, Curitiba, Belo Horizonte, "
    "Porto Alegre, Recife, Salvador e Fortaleza — 1 cliente por cidade. "
    "Uma estratégia regional em São Paulo e Rio pode acelerar o crescimento."
)

# Perguntas e respostas — múltiplas variações por tema para ampliar cobertura do cache
_DEMO_QA: list[tuple[str, str]] = [
    # Clientes
    ("Quantos clientes temos?", _CLIENTES_RESP),
    ("Quantas pessoas temos cadastradas?", _CLIENTES_RESP),
    ("Qual o número de clientes?", _CLIENTES_RESP),
    ("Quantos clientes estão no sistema?", _CLIENTES_RESP),
    ("Me mostra o total de clientes", _CLIENTES_RESP),
    # Produtos
    ("Quantos produtos temos no catálogo?", _PRODUTOS_RESP),
    ("Me mostra os produtos", _PRODUTOS_RESP),
    ("Quais são os produtos disponíveis?", _PRODUTOS_RESP),
    ("Quantos itens temos no estoque?", _PRODUTOS_RESP),
    ("Liste os produtos", _PRODUTOS_RESP),
    # Pedidos
    ("Qual o total de pedidos?", _PEDIDOS_RESP),
    ("Quantos pedidos temos?", _PEDIDOS_RESP),
    ("Quantas vendas foram feitas?", _PEDIDOS_RESP),
    ("Me mostra o número de pedidos", _PEDIDOS_RESP),
    # Receita
    ("Qual a receita total?", _RECEITA_RESP),
    ("Qual o faturamento total?", _RECEITA_RESP),
    ("Quanto faturamos no total?", _RECEITA_RESP),
    ("Qual o valor total das vendas?", _RECEITA_RESP),
    ("Qual a receita gerada?", _RECEITA_RESP),
    # Produto top
    ("Qual produto mais vendido?", _PRODUTO_TOP_RESP),
    ("Qual o produto que mais vende?", _PRODUTO_TOP_RESP),
    ("Qual o item mais popular?", _PRODUTO_TOP_RESP),
    ("Qual produto tem mais vendas?", _PRODUTO_TOP_RESP),
    # Inativos
    ("Quais clientes estão inativos?", _INATIVOS_RESP),
    ("Quem são os clientes inativos?", _INATIVOS_RESP),
    ("Quais clientes não estão ativos?", _INATIVOS_RESP),
    # MRR / receita por cliente
    ("Qual cliente tem maior receita mensal?", _MRR_RESP),
    ("Qual o cliente que paga mais?", _MRR_RESP),
    ("Quem é o cliente mais valioso?", _MRR_RESP),
    ("Qual o MRR?", _MRR_RESP),
    # Planos
    ("Quais são os planos disponíveis?", _PLANOS_RESP),
    ("Que planos existem?", _PLANOS_RESP),
    ("Quais os tipos de plano?", _PLANOS_RESP),
    # Produtos caros
    ("Mostre os produtos mais caros", _CAROS_RESP),
    ("Quais os produtos mais caros?", _CAROS_RESP),
    ("Qual o produto mais caro?", _CAROS_RESP),
    # Cidades
    ("Qual cidade tem mais clientes?", _CIDADES_RESP),
    ("De quais cidades são nossos clientes?", _CIDADES_RESP),
    ("Qual a distribuição geográfica dos clientes?", _CIDADES_RESP),
    (
        "Mostre os produtos mais caros",
        "Os 3 produtos mais caros são: Notebook Ultra (R$ 4.599,90), Monitor 4K (R$ 2.399,90) e Headset Gamer (R$ 599,90). "
        "Todos são Eletrônicos ou Periféricos de alto valor — considere garantia estendida como upsell nesses itens.",
    ),
    (
        "Qual cidade tem mais clientes?",
        "Cada cidade tem 1 cliente no momento: São Paulo, Rio de Janeiro, Curitiba, Belo Horizonte, Porto Alegre, "
        "Recife, Salvador e Fortaleza. A base está bem distribuída geograficamente — "
        "uma estratégia regional pode acelerar o crescimento em hubs como São Paulo e Rio.",
    ),
]


def seed_demo_cache(db_url: str) -> None:
    """Injeta Q&A fixos no cache semântico para o banco demo. Não chama o agente."""
    if "demo.db" not in db_url:
        return
    try:
        from app.agent import _get_semantic_cache
        cache, _ = _get_semantic_cache()

        # Verifica quantas entradas já existem para não duplicar
        existing = cache.count()
        if existing >= len(_DEMO_QA):
            logger.info("Cache demo já populado (%d entradas), pulando warmup.", existing)
            return

        logger.info("Populando cache semântico com %d Q&A do banco demo...", len(_DEMO_QA))
        for question, answer in _DEMO_QA:
            cache.add(
                ids=[str(uuid.uuid4())],
                documents=[question],       # embedding gerado da pergunta
                metadatas=[{"answer": answer, "source": "warmup"}],
            )
        logger.info("Cache semântico populado com sucesso.")
    except Exception:
        logger.warning("Warmup do cache falhou (Ollama offline?), continuando sem cache.", exc_info=True)


async def warmup_agent(db_url: str) -> None:
    """
    Roda perguntas genéricas no agente em background para qualquer banco.
    Use após conectar um banco customizado para aquecer o cache.
    """
    import asyncio
    from app.agent import run_prompt

    questions = [
        "Quantos registros existem em cada tabela?",
        "Quais são as tabelas disponíveis?",
        "Mostre um resumo geral dos dados.",
    ]
    for q in questions:
        try:
            await asyncio.to_thread(run_prompt, db_url, q)
            logger.info("Warmup: '%s' cacheado.", q)
        except Exception:
            logger.warning("Warmup: falha ao processar '%s'.", q, exc_info=True)
