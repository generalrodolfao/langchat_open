"""
Camada de banco de dados.
Gerencia conexões SQLAlchemy e expõe utilitários para o agente SQL.
"""
import json
import logging
import re
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text
from langchain_community.utilities import SQLDatabase

logger = logging.getLogger(__name__)


# ── Registro de conexões ativas ───────────────────────────────────────────────
_engines: dict[str, sa.Engine] = {}


def get_engine(url: str) -> sa.Engine:
    """Retorna (ou cria) um engine para a URL fornecida."""
    if url not in _engines:
        _engines[url] = sa.create_engine(url)
    return _engines[url]


def get_langchain_db(url: str, include_tables: list[str] | None = None) -> SQLDatabase:
    """Retorna um SQLDatabase do LangChain conectado à URL."""
    kwargs: dict[str, Any] = {}
    if include_tables:
        kwargs["include_tables"] = include_tables
    return SQLDatabase.from_uri(url, **kwargs)


def list_tables(url: str) -> list[str]:
    """Lista as tabelas disponíveis no banco."""
    engine = get_engine(url)
    inspector = sa.inspect(engine)
    return inspector.get_table_names()


def run_raw_query(url: str, sql: str) -> list[dict]:
    """Executa uma query SQL bruta e retorna lista de dicts."""
    engine = get_engine(url)
    with engine.connect() as conn:
        result = conn.execute(text(sql))
        cols = list(result.keys())
        rows = result.fetchall()
    return [dict(zip(cols, row)) for row in rows]


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def get_table_sample(url: str, table: str, limit: int = 5) -> list[dict]:
    """Retorna uma amostra de linhas de uma tabela."""
    if not _SAFE_IDENTIFIER.match(table):
        raise ValueError(f"Nome de tabela inválido: {table!r}")
    limit = max(1, min(int(limit), 500))
    return run_raw_query(url, f"SELECT * FROM {table} LIMIT {limit}")


# ── Demo: popula um SQLite de exemplo ────────────────────────────────────────
def seed_demo_db(url: str) -> None:
    """Cria e popula banco demo com ~60 clientes, 20 produtos e ~1400 pedidos (2024-2026)."""
    import random
    from datetime import date, timedelta
    from faker import Faker

    fake = Faker("pt_BR")
    random.seed(42)
    Faker.seed(42)

    engine = get_engine(url)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT,
                cidade TEXT,
                plano TEXT,
                receita_mensal REAL,
                ativo INTEGER DEFAULT 1
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER REFERENCES clientes(id),
                produto TEXT NOT NULL,
                quantidade INTEGER NOT NULL,
                valor_unitario REAL NOT NULL,
                data_pedido TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                categoria TEXT,
                preco REAL NOT NULL,
                estoque INTEGER NOT NULL
            )
        """))

        if conn.execute(text("SELECT COUNT(*) FROM clientes")).scalar() > 0:
            return

        # ── Produtos ──────────────────────────────────────────────────────────
        produtos_data = [
            ("Notebook Ultra",        "Eletrônicos",   4599.90, 23),
            ("Notebook Pro Max",       "Eletrônicos",   6299.90, 12),
            ("Monitor 4K",             "Eletrônicos",   2399.90, 34),
            ("Monitor Ultrawide",      "Eletrônicos",   3199.90, 18),
            ("Mouse Ergonômico",       "Periféricos",    189.90, 145),
            ("Mouse Gamer",            "Periféricos",    279.90, 98),
            ("Teclado Mecânico",       "Periféricos",    349.90, 87),
            ("Teclado Sem Fio",        "Periféricos",    229.90, 76),
            ("Headset Gamer",          "Periféricos",    599.90, 61),
            ("Headset Bluetooth",      "Periféricos",    449.90, 55),
            ("Webcam HD",              "Periféricos",    299.90, 42),
            ("Webcam 4K",              "Periféricos",    599.90, 28),
            ("SSD 1TB",                "Armazenamento",  499.90, 118),
            ("SSD 2TB",                "Armazenamento",  849.90, 64),
            ("HD Externo 4TB",         "Armazenamento",  399.90, 89),
            ("Hub USB-C",              "Periféricos",    149.90, 200),
            ("Dock Station",           "Periféricos",    699.90, 37),
            ("Cadeira Gamer",          "Móveis",        1299.90, 45),
            ("Mesa Ajustável",         "Móveis",        2199.90, 22),
            ("Suporte para Monitor",   "Acessórios",     189.90, 130),
        ]
        for nome, cat, preco, estoque in produtos_data:
            conn.execute(text(
                "INSERT INTO produtos (nome, categoria, preco, estoque) VALUES (:n,:c,:p,:e)"
            ), {"n": nome, "c": cat, "p": preco, "e": estoque})

        produtos_map = {r[0]: r[1] for r in conn.execute(
            text("SELECT nome, preco FROM produtos")
        ).fetchall()}
        produto_nomes = list(produtos_map.keys())

        # Pesos de popularidade por produto (alguns vendem muito mais)
        produto_pesos = [
            8, 3, 5, 2, 15, 10, 12, 8, 7, 5, 6, 3, 14, 6, 8, 18, 4, 5, 2, 9
        ]

        # ── Clientes ──────────────────────────────────────────────────────────
        cidades = [
            "São Paulo", "Rio de Janeiro", "Curitiba", "Belo Horizonte",
            "Porto Alegre", "Recife", "Salvador", "Fortaleza", "Brasília",
            "Manaus", "Belém", "Goiânia", "Florianópolis", "Campinas",
        ]
        planos = [
            ("Starter", 99.90, 0.40),
            ("Pro",     299.90, 0.40),
            ("Enterprise", 999.90, 0.20),
        ]

        clientes_ids = []
        cliente_plano = {}
        for _ in range(60):
            plano_nome, receita, _ = random.choices(
                planos, weights=[p[2] for p in planos]
            )[0]
            ativo = 1 if random.random() > 0.12 else 0
            nome = fake.name()
            email = fake.email()
            cidade = random.choice(cidades)
            conn.execute(text(
                "INSERT INTO clientes (nome, email, cidade, plano, receita_mensal, ativo) "
                "VALUES (:n,:e,:c,:p,:r,:a)"
            ), {"n": nome, "e": email, "c": cidade, "p": plano_nome, "r": receita, "a": ativo})
            cid = conn.execute(text("SELECT last_insert_rowid()")).scalar()
            clientes_ids.append(cid)
            cliente_plano[cid] = plano_nome

        # ── Pedidos 2024-2026 ─────────────────────────────────────────────────
        # Sazonalidade mensal (índice relativo de vendas)
        sazonalidade = {
            1: 0.7,   # janeiro — pós-festas, devagar
            2: 0.75,
            3: 0.85,
            4: 0.90,
            5: 0.95,
            6: 1.0,
            7: 1.05,  # julho — férias
            8: 1.0,
            9: 1.05,
            10: 1.1,
            11: 1.8,  # novembro — Black Friday
            12: 1.5,  # dezembro — Natal
        }

        # Clientes Enterprise compram mais e com maiores quantidades
        plano_freq = {"Starter": 1.0, "Pro": 2.0, "Enterprise": 4.0}

        start = date(2024, 1, 1)
        end = date(2026, 4, 18)
        delta = (end - start).days

        pedidos = []
        for cid in clientes_ids:
            plano = cliente_plano[cid]
            freq = plano_freq[plano]
            # Número base de pedidos no período proporcional à frequência
            n_pedidos = int(random.gauss(freq * 18, freq * 5))
            n_pedidos = max(1, n_pedidos)

            for _ in range(n_pedidos):
                # Escolhe data com peso sazonal
                for _ in range(20):  # tenta até achar dia válido
                    dias = random.randint(0, delta)
                    d = start + timedelta(days=dias)
                    if random.random() < sazonalidade[d.month] / 1.8:
                        break

                produto = random.choices(produto_nomes, weights=produto_pesos)[0]
                preco_base = produtos_map[produto]

                # Pequena variação de preço (promoções, descontos)
                variacao = random.uniform(0.85, 1.05)
                preco_final = round(preco_base * variacao, 2)

                # Quantidade maior em planos maiores e no Black Friday
                max_qty = 3 if plano == "Starter" else (5 if plano == "Pro" else 8)
                if d.month == 11:
                    max_qty += 2
                quantidade = random.choices(
                    range(1, max_qty + 1),
                    weights=[max_qty - i for i in range(max_qty)]
                )[0]

                pedidos.append({
                    "cid": cid,
                    "produto": produto,
                    "quantidade": quantidade,
                    "valor": preco_final,
                    "data": d.isoformat(),
                })

        random.shuffle(pedidos)
        for p in pedidos:
            conn.execute(text(
                "INSERT INTO pedidos (cliente_id, produto, quantidade, valor_unitario, data_pedido) "
                "VALUES (:c,:p,:q,:v,:d)"
            ), {"c": p["cid"], "p": p["produto"], "q": p["quantidade"],
                "v": p["valor"], "d": p["data"]})
