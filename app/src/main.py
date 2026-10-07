"""Електронний щоденник nz.ua — Flet-застосунок (Android/desktop). Увесь інтерфейс — у `nzua.ui`."""
from flet_secure_storage import SecureStorage

from nzua import AsyncNZClient, FileCache
from nzua.ui.backends.flet import FletBackend
from nzua.ui.diary import DiaryApp, Settings
from storage import SecureTokenStore, data_dir

secure = SecureStorage()
client = AsyncNZClient(token_store=SecureTokenStore(secure), cache=FileCache(data_dir() / "cache.json"))
DiaryApp(client, backend=FletBackend(setup=lambda page: page.services.append(secure)),
         settings=Settings.load(data_dir() / "ui.json")).run()
