"""Ponto de entrada: python run.py

Cria (ou atualiza) o banco automaticamente e sobe o servidor local.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = app.config["HOST"]
    port = app.config["PORT"]
    print(f"\n  Sistema PRF em http://{host}:{port}  (Ctrl+C para parar)\n")
    app.run(host=host, port=port, debug=app.config["DEBUG"])
