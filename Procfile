release: flask db upgrade || echo "no migrations yet — tables auto-created"
web: gunicorn run:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120
