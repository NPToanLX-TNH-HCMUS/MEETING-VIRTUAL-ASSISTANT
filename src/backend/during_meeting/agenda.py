confirmed_agendas: dict[str, list[dict]] = {}


def receive_agenda(meeting_id: str, items: list[dict]) -> None:
    confirmed_agendas[meeting_id] = items