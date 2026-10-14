"""Liga os consumidores de eventos de domínio (conquistas e notificações)."""

from app.services import achievement_service, domain_events, notification_service


def register() -> None:
    domain_events.subscribe(notification_service.on_event)
    domain_events.subscribe(achievement_service.on_event)
