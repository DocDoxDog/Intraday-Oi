from services.telegram_control import TelegramAuthorizer, TelegramControlPlane, TelegramPrincipal, TelegramRole
from src.telegram_bot import TelegramPollingWorker

class FakeTransport:
    def __init__(self):
        self.sent = []
        self.callbacks = []
    def get_updates(self, offset=None):
        return []
    def send(self, chat_id, response):
        self.sent.append((chat_id, response))
    def answer_callback(self, callback_id):
        self.callbacks.append(callback_id)

def test_polling_worker_processes_authorized_command():
    principal = TelegramPrincipal("10", "20", TelegramRole.ADMIN)
    control = TelegramControlPlane(TelegramAuthorizer({("10", "20"): principal}))
    transport = FakeTransport()
    worker = TelegramPollingWorker(control, transport)
    assert worker.process_update({"update_id": 1, "message": {"from": {"id": 10}, "chat": {"id": 20}, "text": "/help"}})
    assert "AI MARKET INTELLIGENCE" in transport.sent[0][1].text

def test_callback_is_acknowledged():
    principal = TelegramPrincipal("10", "20", TelegramRole.ADMIN)
    control = TelegramControlPlane(TelegramAuthorizer({("10", "20"): principal}))
    transport = FakeTransport()
    worker = TelegramPollingWorker(control, transport)
    worker.process_update({
        "update_id": 2,
        "callback_query": {
            "id": "cb-1", "from": {"id": 10}, "data": "levels",
            "message": {"chat": {"id": 20}},
        },
    })
    assert transport.callbacks == ["cb-1"]
