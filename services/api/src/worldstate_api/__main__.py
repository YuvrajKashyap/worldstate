import uvicorn

from worldstate_api.settings import Settings


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "worldstate_api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
    )


if __name__ == "__main__":
    main()
