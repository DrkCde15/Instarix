"""Funções de métricas (insights) da conta e dos posts."""

from instagrapi import Client


def insights_conta(cl: Client) -> dict:
    """Retorna as métricas gerais da conta."""
    return cl.insights_account()


def insights_post(cl: Client, media_pk: str | int) -> dict:
    """Retorna as métricas de um post específico."""
    return cl.insights_media(media_pk)


def insights_feed(
    cl: Client,
    tipo_post: str = "ALL",
    periodo: str = "TWO_YEARS",
    ordenar_por: str = "REACH_COUNT",
    quantidade: int = 0,
):
    """Lista métricas de vários posts.

    tipo_post: ALL, CAROUSEL_V2, IMAGE, SHOPPING ou VIDEO.
    periodo: ONE_WEEK, ONE_MONTH, THREE_MONTHS, SIX_MONTHS, ONE_YEAR ou TWO_YEARS.
    ordenar_por: REACH_COUNT, LIKE_COUNT, FOLLOW, SHARE_COUNT, COMMENT_COUNT,
                 IMPRESSION_COUNT, PROFILE_VIEW, VIDEO_VIEW_COUNT ou SAVE_COUNT.
    """
    return cl.insights_media_feed_all(
        post_type=tipo_post,
        time_frame=periodo,
        data_ordering=ordenar_por,
        count=quantidade,
    )
