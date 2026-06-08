# MySignatures — Sistema de Assinatura Eletrônica

Plataforma de assinatura eletrônica de documentos com verificação facial, OTP,
selo digital em PDF e validação pública de assinaturas via acumulador RSA.

O repositório é dividido em dois projetos:

| Pasta | Stack | Descrição |
|-------|-------|-----------|
| [`e-signature-api-python/`](e-signature-api-python/) | Python · FastAPI · PostgreSQL | API REST (back-end) |
| [`e_signature_frontend/`](e_signature_frontend/) | Flutter (Web) | Aplicação cliente (front-end) |

---

## Pré-requisitos

Instale antes de começar:

- **Python 3.12** — https://www.python.org/downloads/
- **PostgreSQL 14+** — https://www.postgresql.org/download/
- **Flutter SDK 3.9+** (Dart 3.9+) — https://docs.flutter.dev/get-started/install
- **Git**

Confira as versões:

```bash
python --version    # Python 3.12.x
flutter --version   # Flutter 3.9 ou superior
psql --version
```

---

## Visão geral das portas

| Serviço | URL padrão |
|---------|-----------|
| API (FastAPI) | http://localhost:8000 |
| Docs interativas (Swagger) | http://localhost:8000/docs |
| Front-end (Flutter Web) | http://localhost:53398 |

> O CORS da API já vem liberado para `http://localhost:53398`, por isso o
> front-end deve ser executado **exatamente nessa porta** (instruções abaixo).

---

## 1. Back-end — `e-signature-api-python`

### 1.1. Criar o banco de dados

Crie um banco PostgreSQL chamado `e_signature` (ajuste usuário/senha conforme
sua instalação):

```bash
psql -U postgres -c "CREATE DATABASE e_signature;"
```

### 1.2. Criar e ativar o ambiente virtual

```bash
cd e-signature-api-python
python -m venv .venv
```

Ative o ambiente:

```powershell
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1
```

```bash
# Linux / macOS
source .venv/bin/activate
```

### 1.3. Instalar dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> O `requirements.txt` inclui `insightface`, `onnxruntime` e `opencv-python`
> (verificação facial). A primeira instalação pode demorar alguns minutos.

### 1.4. Configurar variáveis de ambiente

Crie um arquivo `.env` dentro de `e-signature-api-python/` com o conteúdo abaixo
(ajuste as credenciais do PostgreSQL):

```env
# Obrigatórias
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/e_signature
JWT_SECRET=troque-por-uma-chave-secreta-forte

# Opcionais — URLs base
FRONTEND_BASE_URL=http://localhost:53398
PUBLIC_BASE_URL=http://localhost:8000

# Opcionais — segredo dedicado para o acumulador (recomendado em produção)
# ACCUMULATOR_HMAC_SECRET=outra-chave-secreta

# Opcionais — envio de e-mail (recuperação de senha, notificações)
# EMAIL_USER=seu-email@gmail.com
# EMAIL_PASSWORD=sua-senha-de-app
# SMTP_SERVER=smtp.gmail.com
# SMTP_PORT=465

# Opcionais — WhatsApp via Twilio
# TWILIO_ACCOUNT_SID=...
# TWILIO_AUTH_TOKEN=...
# TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
# TWILIO_STATUS_CALLBACK_URL=https://<hash>.ngrok.io/webhooks/twilio-status
```

> **Apenas `DATABASE_URL` e `JWT_SECRET` são obrigatórias** para subir a API
> localmente. As demais habilitam recursos extras (e-mail, WhatsApp).

### 1.5. Rodar as migrações do banco

```bash
alembic upgrade head
```

Isso cria todas as tabelas no banco `e_signature`.

### 1.6. Iniciar a API

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse a documentação interativa em **http://localhost:8000/docs** para
confirmar que está no ar.

---

## 2. Front-end — `e_signature_frontend`

> Abra um **novo terminal** (deixe a API rodando no anterior).

### 2.1. Instalar dependências

```bash
cd e_signature_frontend
flutter pub get
```

### 2.2. Habilitar suporte a Web (caso ainda não esteja)

```bash
flutter config --enable-web
```

### 2.3. Executar o app

O app é uma aplicação Flutter **Web**. Execute-o na porta `53398` para casar com
o CORS da API:

```bash
flutter run -d chrome --web-port 53398
```

A URL base da API é lida da variável de compilação `API_BASE_URL`, com valor
padrão `http://localhost:8000`. Se a sua API estiver em outro endereço, passe:

```bash
flutter run -d chrome --web-port 53398 --dart-define=API_BASE_URL=http://localhost:8000
```

---

## 3. Checklist do primeiro start

1. PostgreSQL rodando e banco `e_signature` criado.
2. `e-signature-api-python/.env` preenchido (`DATABASE_URL` + `JWT_SECRET`).
3. `alembic upgrade head` executado sem erros.
4. API no ar em http://localhost:8000/docs.
5. `flutter pub get` concluído.
6. Front-end no ar em http://localhost:53398.

---

## Estrutura do projeto

```
MySignatures/
├── e-signature-api-python/      # Back-end (FastAPI)
│   ├── app/
│   │   ├── api/v1/endpoints/     # Controllers (auth, documents, OTP, face, etc.)
│   │   ├── core/                 # Config e segurança
│   │   ├── db/                   # Sessão e engine do banco
│   │   ├── models/               # Modelos SQLAlchemy
│   │   ├── schemas/              # Schemas Pydantic
│   │   ├── services/             # Regras de negócio (assinatura, facial, PDF)
│   │   └── main.py               # Ponto de entrada da API
│   ├── alembic/                  # Migrações do banco
│   └── requirements.txt
│
└── e_signature_frontend/         # Front-end (Flutter Web)
    ├── lib/
    │   ├── core/                 # Constantes (ex.: api_constants.dart) e utils
    │   ├── data/                 # Models, repositories e services
    │   ├── presentation/         # Telas, providers e widgets
    │   └── main.dart             # Ponto de entrada do app
    └── pubspec.yaml
```

---

## Solução de problemas

- **`DATABASE_URL não configurada ou erro ao inicializar motor`** — verifique se
  o `.env` existe na pasta `e-signature-api-python/` e se o PostgreSQL está
  online. A `DATABASE_URL` deve usar o driver `postgresql+asyncpg://`.
- **Erro de CORS no navegador** — rode o front-end na porta `53398` ou adicione
  a sua porta em `BACKEND_CORS_ORIGINS` no `.env` da API.
- **Front-end não conecta na API** — confirme que a API está em
  `http://localhost:8000` ou ajuste com `--dart-define=API_BASE_URL=...`.
- **Falha ao instalar `insightface`/`onnxruntime`** — atualize o `pip`
  (`pip install --upgrade pip`) e garanta que está usando Python 3.12.
```
