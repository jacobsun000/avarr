from avarr.app import app, create_app


__all__ = ["app", "create_app"]


def main() -> None:
    import uvicorn

    uvicorn.run("avarr.app:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
