# Birdie Tracking Dashboard — Setup

## 1. Google Service Account (una sola vez)

1. Ve a [console.cloud.google.com](https://console.cloud.google.com).
2. Crea un proyecto (o selecciona uno existente).
3. Activa la API: **APIs y servicios → Biblioteca → Google Sheets API → Habilitar**.
4. Ve a **IAM y administración → Cuentas de servicio → Crear cuenta de servicio**.
   - Nombre: `birdie-tracking`
   - Rol: ninguno requerido a nivel de proyecto
5. Dentro de la cuenta creada: **Claves → Agregar clave → JSON**.
   Descarga el archivo y renómbralo `service-account.json`.
6. Coloca `service-account.json` en la raíz del proyecto (junto a `main.py`).
   > ⚠️ Nunca subas este archivo a git. Ya está en `.gitignore`.

---

## 2. Compartir el Google Sheet con la Service Account

1. Abre el archivo Google Sheets con la hoja `ag-grid`.
2. Clic en **Compartir**.
3. Pega el correo de la service account (campo `client_email` dentro de `service-account.json`).
4. Permiso: **Lector** (viewer).
5. Copia el ID del Spreadsheet de la URL:
   ```
   https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
   ```

---

## 3. Variables de entorno

```bash
cp .env.example .env
# edita .env:
GOOGLE_SHEETS_ID=<pega el SPREADSHEET_ID aquí>
GOOGLE_SHEET_NAME=ag-grid          # nombre exacto de la hoja
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
```

---

## 4. Instalar dependencias y correr

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Abre [http://localhost:8000](http://localhost:8000).

---

## 5. Estructura del proyecto

```
Coppel-logistica/
├── main.py                 # FastAPI app (rutas + static)
├── sheets.py               # Cliente Google Sheets API v4
├── processor.py            # Cálculo de métricas ATD/ATA
├── requirements.txt
├── .env                    # Variables de entorno (no en git)
├── .env.example
├── service-account.json    # Credenciales SA (no en git)
└── frontend/
    └── index.html          # Dashboard (servido como estático)
```

---

## 6. Endpoint `/api/data` — respuesta JSON

| Campo | Descripción |
|-------|-------------|
| `summary` | KPIs globales: totales, ATD/ATA exact/within1/mean_diff |
| `atd_dist` | Distribución de diferencias ATD `[{diff, count}]` |
| `ata_dist` | Distribución de diferencias ATA (solo Discharged/Arrived) |
| `ata_navieras` | Exacto / ±1d / sesgo por naviera (ATA) |
| `ata_pods` | Exacto / ±1d / sesgo por puerto de destino (ATA) |
| `eta_prediction` | ETA Birdie vs ATA real (contenedores Discharged) |
| `navieras` | Precisión ATD por naviera |
| `puertos` | Precisión ATD por puerto de origen (top 12) |
| `comment_groups` | Frecuencia de comentarios Coppel |
| `table` | Filas crudas completas para la tabla del dashboard |

---

## 7. `.gitignore` recomendado

```
.env
service-account.json
.venv/
__pycache__/
*.pyc
```
