"""Modelo do arquivo WSGI do PythonAnywhere.

NAO e usado localmente. Copie TODO o conteudo abaixo para o arquivo WSGI que o
PythonAnywhere cria em /var/www/SEUUSUARIO_pythonanywhere_com_wsgi.py
(apagando o que estiver la). Veja DEPLOY.md.

Nao ha nada para editar: o caminho da pasta pessoal e descoberto sozinho.
"""

import os
import sys

# 1. Caminho do projeto, descoberto a partir da pasta pessoal do usuario.
PROJETO = os.path.join(os.path.expanduser("~"), "System-PRF")
if PROJETO not in sys.path:
    sys.path.insert(0, PROJETO)

# 2. Fuso horario. O servidor roda em UTC; sem isto, tudo registrado depois das
#    21h no Brasil seria gravado com a data do dia seguinte.
os.environ.setdefault("PRF_TIMEZONE", "America/Sao_Paulo")

# 3. Producao: cookie de sessao so por HTTPS e sem modo debug.
os.environ.setdefault("PRF_HTTPS", "1")
os.environ.setdefault("PRF_DEBUG", "0")

# 4. PRF_SECRET_KEY e PRF_PASSWORD_HASH vem do arquivo .env dentro do projeto.

from run import app as application  # noqa: E402
