"""Exemplo do módulo funcs.insights: métricas da conta e dos posts."""

from funcs import insights
from funcs.client import get_client

cl = get_client()

# Métricas gerais da conta.
conta = insights.insights_conta(cl)
print(conta)

# Métricas de um post específico.
post = insights.insights_post(cl, "MEDIA_PK")
print(post)

# Métricas de vários posts (últimos 30 dias, ordenados por alcance).
feed = insights.insights_feed(
    cl,
    tipo_post="ALL",
    periodo="ONE_MONTH",
    ordenar_por="REACH_COUNT",
    quantidade=20,
)
print(f"{len(feed)} posts analisados")
