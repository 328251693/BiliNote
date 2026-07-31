import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.staticfiles import StaticFiles
from dotenv import load_dotenv

from app.db.init_db import init_db
from app.db.provider_dao import seed_default_providers
from app.exceptions.exception_handlers import register_exception_handlers
# from app.db.model_dao import init_model_table
# from app.db.provider_dao import init_provider_table
from app.utils.logger import get_logger
from app import create_app
from app.services.transcriber_config_manager import TranscriberConfigManager
from events import register_handler
from ffmpeg_helper import ensure_ffmpeg_or_raise

logger = get_logger(__name__)
load_dotenv()

# ?? .env ????
static_path = os.getenv('STATIC', '/static')
out_dir = os.getenv('OUT_DIR', './static/screenshots')

# ?????????static ? static/screenshots?
static_dir = "static"
uploads_dir = "uploads"
if not os.path.exists(static_dir):
    os.makedirs(static_dir)
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)

if not os.path.exists(out_dir):
    os.makedirs(out_dir)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ?????? 5 ???????? + ??????? [startup N/5 FAILED] ???
    # ????? docker logs ??????????????????????????????
    try:
        logger.info("[startup 1/5] register_handler() ? ???????")
        register_handler()

        logger.info("[startup 2/5] init_db() ? ??? SQLite ???")
        init_db()

        logger.info("[startup 3/5] TranscriberConfigManager ? ???????")
        # ??????????????????????????????
        # ????????????? mlx-whisper ???????????????????
        _cfg = TranscriberConfigManager().get_config()
        logger.info(
            f"           ?????: type={_cfg['transcriber_type']}, "
            f"model_size={_cfg['whisper_model_size']}"
        )

        logger.info("[startup 4/5] seed_default_providers() ? ????? LLM ???")
        seed_default_providers()

        logger.info("[startup 5/5] ?????????")
    except Exception:
        logger.exception("[startup FAILED] ???????????????????? restart ????????")
        raise

    yield

app = create_app(lifespan=lifespan)

# ??????? web ? + Tauri ??? + ??????chrome/edge/firefox?
# ? regex ??? chrome-extension://<id> ? id ????????????
# Tauri 2 ???? webview origin ?????????
#   - macOS:   tauri://localhost  ???????
#   - Windows: https://tauri.localhost  ?Edge WebView2?
#   - Linux:   http://tauri.localhost   ?WebKitGTK?
# ??????????? fetch ?? 200 ? browser ?? CORS ??????
# ??????????????????? 200 OK?
CORS_ORIGIN_REGEX = (
    r"^https://note\.aividox\.com$"
    r"|^https://www\.aividox\.com$"
    r"|^chrome-extension://[a-z]+$"
    r"|^moz-extension://.+$"
    r"|^http://(localhost|127\.0\.0\.1)(:\d+)?$"
    r"|^tauri://localhost$"
    r"|^https?://tauri\.localhost$"
)

# ?????????????????????????
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "https://note.aividox.com,https://www.aividox.com",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
register_exception_handlers(app)
app.mount(static_path, StaticFiles(directory=static_dir), name="static")
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")









if __name__ == "__main__":
    port = int(os.getenv("BACKEND_PORT", 8483))
    host = os.getenv("BACKEND_HOST", "0.0.0.0")
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)
