web: python3 -c "from app import app, init_db; app.app_context().push(); init_db()" && gunicorn app:app --bind 0.0.0.0:${PORT:-9090} --workers 1 --threads 8 --timeout 120
