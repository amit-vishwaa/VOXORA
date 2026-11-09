"""Command line: python manage.py migrate | seed | reset | run [--port 5000]"""
import os
import sys
from pathlib import Path

from app import create_app, db, config


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    app = create_app()
    if cmd == "migrate":
        with app.app_context():
            print("Applied:", db.run_migrations() or "nothing new")
    elif cmd == "seed":
        from app.seed import seed, admin_creds
        with app.app_context():
            print("Seeded sample data." if seed() else "Database already has users; skipped (use 'reset' to start over).")
            print("Super admin login:", admin_creds()[0])
    elif cmd == "reset":
        dbf = Path(app.config["DATABASE"])
        for suffix in ("", "-wal", "-shm"):
            Path(str(dbf) + suffix).unlink(missing_ok=True)
        for f in Path(app.config["RECORDINGS_DIR"]).glob("*.wav"):
            f.unlink()
        app = create_app()
        from app.seed import seed
        with app.app_context():
            seed()
        print("Database reset and re-seeded.")
    elif cmd == "run":
        port = int(os.environ.get("PORT", 5000))
        host = os.environ.get("HOST", "127.0.0.1")
        print(f"Voxora AI running at http://{host}:{port}  (simulated providers)")
        try:
            from waitress import serve
            serve(app, host=host, port=port, threads=8)
        except ImportError:
            app.run(host=host, port=port)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
