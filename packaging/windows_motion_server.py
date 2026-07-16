from windows_runtime import prepare_runtime


prepare_runtime()

from motion_server.server import main


if __name__ == "__main__":
    main()
