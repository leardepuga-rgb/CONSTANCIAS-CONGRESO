# Generador de constancias – Congreso de Enfermería

App web (Streamlit) para generar constancias en PDF por rol, imprimirlas o enviarlas por correo.

## Estructura

```
constancias_app/
├── app.py                  # Interfaz (4 pestañas)
├── core/
│   ├── generator.py        # Plantilla + nombre -> PDF, ZIP, PDF único, vista previa
│   └── mailer.py           # Envío por SMTP con adjunto
├── data/                   # Se crea sola: plantillas, fuentes y config.json
├── ejemplo_participantes.csv
├── requirements.txt
└── README.md
```

## Ejecutar en tu computadora

1. Instala Python 3.10 o superior (python.org; en Windows marca "Add Python to PATH").
2. Abre una terminal dentro de la carpeta `constancias_app` y ejecuta:

```bash
python -m venv venv
venv\Scripts\activate          # Windows   (Mac/Linux: source venv/bin/activate)
pip install -r requirements.txt
streamlit run app.py
```

3. Se abre el navegador en http://localhost:8501.

## Cómo usarla

1. **Plantillas**: elige un rol, sube su diseño (PNG/JPG/PDF) y ajusta posición, fuente, tamaño y color
   del nombre. La vista previa es el PDF real. Repite con los 4 roles (o usa "Copiar estilo").
2. **Participantes**: sube Excel/CSV con nombre, correo y rol. Se aceptan variantes como
   "Asistente", "ponente", "Comite organizador", "Logística". Puedes editar la tabla y elegir por
   persona la **Entrega**: Electrónico, Impresión o Ambos.
3. **Generar y entregar**:
   - *Individual*: busca a la persona, descarga su PDF o envíale el correo.
   - *Masivo*: ZIP con todos los PDF, un **PDF único** con las de impresión, o envío masivo de correos.
4. **Correo**: servidor SMTP, mensaje con `{nombre}`, `{rol}`, `{evento}` y botón de probar conexión.

### Gmail
Activa la verificación en 2 pasos y crea una **contraseña de aplicación**
(Cuenta de Google → Seguridad → Contraseñas de aplicaciones). Servidor `smtp.gmail.com`, puerto `587`.
Gmail limita los envíos (~500/día en cuentas personales): usa una pausa de 1–2 s entre correos.
Outlook/Microsoft 365: `smtp.office365.com`, puerto `587`.

La contraseña no se guarda en disco. Para no escribirla cada vez, define la variable de entorno
`SMTP_PASSWORD` antes de iniciar la app.

## Desplegar en línea (opcional)

**Streamlit Community Cloud** (gratis): sube la carpeta a un repositorio **privado** de GitHub, entra a
share.streamlit.io, elige `app.py` y despliega. Ojo:
- El disco es temporal: las plantillas y ajustes se pierden al reiniciar la app. Para un evento puntual
  funciona; si quieres que persistan, usa un servidor propio (VPS) o Docker con un volumen en `data/`.
- Define `SMTP_PASSWORD` en *Settings → Secrets* (`SMTP_PASSWORD = "..."`) o en la pestaña Correo.
- No subas a GitHub las bases de datos de participantes (datos personales).

## Ajustes avanzados

- Más campos en la constancia (folio, fecha, nombre de la ponencia): en `core/generator.py`,
  `make_certificate` dibuja un solo texto; basta repetir el bloque `c.drawString` con otra posición.
- Fuentes propias: sube un `.ttf` en la pestaña Plantillas (sirve para acentos y estilos de letra cursiva).
