"""Generador de constancias para congreso de enfermería (Streamlit)."""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from core import generator as gen
from core import mailer

BASE = Path(__file__).parent
DATA = BASE / "data"
TPL_DIR = DATA / "plantillas"
FONT_DIR = DATA / "fuentes"
CFG_FILE = DATA / "config.json"
for d in (TPL_DIR, FONT_DIR):
    d.mkdir(parents=True, exist_ok=True)

ENTREGAS = ["Electrónico", "Impresión", "Ambos"]
SAMPLE_NAME = "María Fernanda López de la Rosa"

DEFAULT_CFG = {
    "evento": "Congreso de Enfermería",
    "roles": {r: {"template": None, "style": dict(gen.DEFAULT_STYLE)} for r in gen.ROLES},
    "smtp": {"host": "smtp.gmail.com", "port": 587, "user": "", "from_name": ""},
    "email": {
        "subject": "Tu constancia – {evento}",
        "body": (
            "Hola {nombre},\n\n"
            "Gracias por tu participación como {rol} en el {evento}.\n"
            "Adjuntamos tu constancia en formato PDF.\n\n"
            "¡Saludos cordiales!\nComité Organizador"
        ),
    },
}


# ------------------------------------------------------------------ config
def load_cfg() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CFG))
    if CFG_FILE.exists():
        saved = json.loads(CFG_FILE.read_text(encoding="utf-8"))
        cfg["evento"] = saved.get("evento", cfg["evento"])
        cfg["smtp"].update(saved.get("smtp", {}))
        cfg["email"].update(saved.get("email", {}))
        for r in gen.ROLES:
            s = saved.get("roles", {}).get(r, {})
            cfg["roles"][r]["template"] = s.get("template")
            cfg["roles"][r]["style"].update(s.get("style", {}))
    return cfg


def save_cfg(cfg: dict) -> None:
    CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def tpl_path(cfg: dict, role: str) -> Path | None:
    name = cfg["roles"][role]["template"]
    p = TPL_DIR / name if name else None
    return p if p and p.exists() else None


def font_choices() -> list[str]:
    return list(gen.BUILTIN_FONTS) + sorted(p.stem for p in FONT_DIR.glob("*.ttf"))


@st.cache_data(show_spinner=False, max_entries=512)
def cached_pdf(path: str, mtime: float, style_json: str, text: str, fonts_mtime: float) -> bytes:
    return gen.make_certificate(path, text, json.loads(style_json), FONT_DIR)


def certificate(cfg: dict, role: str, name: str) -> bytes | None:
    p = tpl_path(cfg, role)
    if not p:
        return None
    fm = max([f.stat().st_mtime for f in FONT_DIR.glob("*.ttf")], default=0)
    return cached_pdf(str(p), p.stat().st_mtime, json.dumps(cfg["roles"][role]["style"], sort_keys=True),
                      name, fm)


def smtp_password() -> str:
    return st.session_state.get("smtp_pass") or os.environ.get("SMTP_PASSWORD", "")


# -------------------------------------------------------------- participantes
def guess(cols: list[str], *keys: str) -> int:
    for i, c in enumerate(cols):
        lc = gen.strip_accents(c).lower()
        if any(k in lc for k in keys):
            return i
    return 0


def read_table(file) -> pd.DataFrame:
    if file.name.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(file, dtype=str)
    raw = file.getvalue()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(io.StringIO(raw.decode(enc)), sep=None, engine="python", dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer el CSV")


def participants_df() -> pd.DataFrame | None:
    return st.session_state.get("participants")


def valid_rows(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Filas con nombre y rol reconocido (el rol se normaliza)."""
    d = df.copy()
    d["Rol"] = d["Rol"].map(lambda r: gen.normalize_role(r) or r)
    d = d[d["Nombre"].fillna("").str.strip().ne("") & d["Rol"].isin(gen.ROLES)]
    return d


def filename_for(role: str, name: str) -> str:
    return f"Constancia_{gen.slugify(role)}_{gen.slugify(name)}.pdf"


# ===================================================================== UI
st.set_page_config(page_title="Constancias – Congreso de Enfermería", page_icon="🎓", layout="wide")
cfg = load_cfg()

st.title("🎓 Generador de constancias")
cfg["evento"] = st.text_input("Nombre del evento (se usa en los correos)", cfg["evento"])

tab_tpl, tab_data, tab_gen, tab_mail = st.tabs(
    ["1️⃣ Plantillas por rol", "2️⃣ Participantes", "3️⃣ Generar y entregar", "4️⃣ Correo"]
)

# ------------------------------------------------------------ 1. Plantillas
with tab_tpl:
    st.caption("Sube un diseño por rol (PNG, JPG o PDF) y ajusta dónde va el nombre. "
               "La vista previa es exactamente el PDF final.")
    ok = {r: bool(tpl_path(cfg, r)) for r in gen.ROLES}
    st.write("  ".join(f"{'✅' if v else '⬜'} {r}" for r, v in ok.items()))

    role = st.radio("Rol a configurar", gen.ROLES, horizontal=True)
    rc = cfg["roles"][role]
    left, right = st.columns([1, 1.4])

    with left:
        up = st.file_uploader(f"Plantilla para {role}", type=["png", "jpg", "jpeg", "pdf"],
                              key=f"up_{role}")
        if up is not None:
            fname = f"{gen.slugify(role)}{Path(up.name).suffix.lower()}"
            for old in TPL_DIR.glob(f"{gen.slugify(role)}.*"):
                old.unlink()
            (TPL_DIR / fname).write_bytes(up.getvalue())
            rc["template"] = fname
            save_cfg(cfg)
            st.success("Plantilla guardada.")

        fup = st.file_uploader("Fuente personalizada .ttf (opcional)", type=["ttf"], key="font_up")
        if fup is not None:
            (FONT_DIR / f"{Path(fup.name).stem}.ttf").write_bytes(fup.getvalue())
            st.success(f"Fuente «{Path(fup.name).stem}» agregada.")

        s = rc["style"]
        fonts = font_choices()
        s["font"] = st.selectbox("Fuente", fonts,
                                 index=fonts.index(s["font"]) if s["font"] in fonts else 0, key=f"f_{role}")
        c1, c2 = st.columns(2)
        s["size"] = c1.number_input("Tamaño", 10, 120, int(s["size"]), key=f"sz_{role}")
        s["color"] = c2.color_picker("Color", s["color"], key=f"col_{role}")
        s["case"] = st.radio("Formato del nombre", ["Tipo título", "MAYÚSCULAS", "Tal cual"],
                             index=["Tipo título", "MAYÚSCULAS", "Tal cual"].index(s["case"]),
                             horizontal=True, key=f"case_{role}")
        s["align"] = st.radio("Alineación", ["left", "center", "right"],
                              index=["left", "center", "right"].index(s["align"]), horizontal=True,
                              format_func={"left": "Izquierda", "center": "Centro", "right": "Derecha"}.get,
                              key=f"al_{role}")
        s["x"] = st.slider("Posición horizontal (%)", 0, 100, int(round(s["x"] * 100)), key=f"x_{role}") / 100
        s["y"] = st.slider("Posición vertical (% desde arriba)", 0, 100, int(round(s["y"] * 100)),
                           key=f"y_{role}") / 100
        s["max_w"] = st.slider("Ancho máximo del nombre (%)", 20, 100, int(round(s["max_w"] * 100)),
                               key=f"mw_{role}") / 100
        sample = st.text_input("Nombre de prueba", SAMPLE_NAME, key="sample")

        b1, b2 = st.columns(2)
        if b1.button("💾 Guardar ajustes", type="primary"):
            save_cfg(cfg)
            st.success("Guardado.")
        if b2.button("📋 Copiar estilo a los otros roles"):
            for r in gen.ROLES:
                cfg["roles"][r]["style"] = dict(s)
            save_cfg(cfg)
            st.success("Estilo copiado.")

    with right:
        pdf = certificate(cfg, role, sample)
        if pdf:
            st.image(gen.render_preview(pdf), width="stretch")
        else:
            st.info("Sube una plantilla para ver la vista previa.")

# ----------------------------------------------------------- 2. Participantes
with tab_data:
    st.caption("Sube tu Excel o CSV con nombre completo, correo y rol.")
    sample_csv = ("Nombre,Correo,Rol\n"
                  "Ana Lucía Pérez Gómez,ana@ejemplo.com,Asistente\n"
                  "Dr. Carlos Ruiz Soto,carlos@ejemplo.com,Ponente\n"
                  "Mtra. Rosa Beltrán,rosa@ejemplo.com,Comité Organizador\n"
                  "Luis Ángel Ortiz,luis@ejemplo.com,Logística\n")
    st.download_button("⬇️ Descargar formato de ejemplo (CSV)", sample_csv.encode("utf-8-sig"),
                       "ejemplo_participantes.csv", "text/csv")

    default_entrega = st.radio("Entrega por defecto", ENTREGAS, horizontal=True,
                               help="Electrónico = solo correo · Impresión = PDF para imprimir · Ambos")
    file = st.file_uploader("Base de datos", type=["xlsx", "xls", "csv"])
    if file is not None:
        try:
            raw = read_table(file)
            cols = list(raw.columns)
            m1, m2, m3 = st.columns(3)
            c_name = m1.selectbox("Columna de nombre", cols, index=guess(cols, "nombre", "name"))
            c_mail = m2.selectbox("Columna de correo", cols, index=guess(cols, "correo", "mail"))
            c_role = m3.selectbox("Columna de rol", cols, index=guess(cols, "rol", "tipo", "role"))
            if st.button("Cargar participantes", type="primary"):
                df = pd.DataFrame({
                    "Nombre": raw[c_name].fillna("").astype(str).str.strip(),
                    "Correo": raw[c_mail].fillna("").astype(str).str.strip(),
                    "Rol": raw[c_role].fillna("").astype(str).map(lambda r: gen.normalize_role(r) or r),
                    "Entrega": default_entrega,
                })
                st.session_state["participants"] = df
        except Exception as e:  # noqa: BLE001
            st.error(f"No pude leer el archivo: {e}")

    df = participants_df()
    if df is not None:
        if st.button("Aplicar entrega por defecto a todos"):
            df["Entrega"] = default_entrega
        edited = st.data_editor(
            df, num_rows="dynamic", width="stretch", key="editor",
            column_config={
                "Rol": st.column_config.SelectboxColumn("Rol", options=gen.ROLES),
                "Entrega": st.column_config.SelectboxColumn("Entrega", options=ENTREGAS, required=True),
            },
        )
        st.session_state["participants"] = edited
        # validaciones
        bad_role = edited[~edited["Rol"].isin(gen.ROLES)]
        bad_mail = edited[edited["Entrega"].isin(["Electrónico", "Ambos"])
                          & ~edited["Correo"].fillna("").map(mailer.is_valid_email)]
        no_tpl = sorted({r for r in edited["Rol"].unique() if r in gen.ROLES and not tpl_path(cfg, r)})
        st.write(f"**{len(edited)}** participantes · "
                 + " · ".join(f"{r}: {(edited['Rol'] == r).sum()}" for r in gen.ROLES))
        if len(bad_role):
            st.warning(f"{len(bad_role)} fila(s) con rol no reconocido (corrígelas en la tabla).")
        if len(bad_mail):
            st.warning(f"{len(bad_mail)} fila(s) con envío electrónico y correo inválido o vacío.")
        if no_tpl:
            st.warning("Falta subir plantilla para: " + ", ".join(no_tpl))

# --------------------------------------------------------- 3. Generar/entregar
with tab_gen:
    df = participants_df()
    if df is None or df.empty:
        st.info("Primero carga los participantes en la pestaña 2.")
    else:
        vr = valid_rows(df, cfg)
        vr = vr[vr["Rol"].map(lambda r: bool(tpl_path(cfg, r)))].reset_index(drop=True)
        if vr.empty:
            st.info("No hay participantes con rol válido y plantilla cargada.")
        else:
            mode = st.radio("¿Qué quieres hacer?", ["👤 Individual", "👥 Masivo"], horizontal=True)

            def mail_fields(row) -> tuple[str, str]:
                f = dict(nombre=row["Nombre"], rol=row["Rol"], evento=cfg["evento"])
                return (mailer.fill_template(cfg["email"]["subject"], **f),
                        mailer.fill_template(cfg["email"]["body"], **f))

            # ---------------- individual
            if mode.startswith("👤"):
                q = st.text_input("Buscar por nombre")
                opts = vr[vr["Nombre"].str.contains(q, case=False, na=False)] if q else vr
                if opts.empty:
                    st.warning("Sin resultados.")
                else:
                    idx = st.selectbox("Participante", opts.index,
                                       format_func=lambda i: f"{vr.loc[i, 'Nombre']}  ·  {vr.loc[i, 'Rol']}")
                    row = vr.loc[idx]
                    pdf = certificate(cfg, row["Rol"], row["Nombre"])
                    cL, cR = st.columns([1.3, 1])
                    cL.image(gen.render_preview(pdf), width="stretch")
                    with cR:
                        st.markdown(f"**{row['Nombre']}**  \n{row['Rol']}  \n{row['Correo'] or '—'}  \n"
                                    f"Entrega: **{row['Entrega']}**")
                        st.download_button("🖨️ Descargar PDF (para imprimir)", pdf,
                                           filename_for(row["Rol"], row["Nombre"]), "application/pdf",
                                           width="stretch")
                        if st.button("📧 Enviar por correo", width="stretch",
                                     disabled=not mailer.is_valid_email(row["Correo"])):
                            subj, body = mail_fields(row)
                            res = mailer.send_many(cfg["smtp"], smtp_password(), [dict(
                                to=row["Correo"], subject=subj, body=body, pdf=pdf,
                                filename=filename_for(row["Rol"], row["Nombre"]))])[0]
                            (st.success if res["status"] == "Enviado" else st.error)(
                                f"{res['status']} {res['detail']}")

            # ---------------- masivo
            else:
                roles_sel = st.multiselect("Roles a incluir", gen.ROLES, default=gen.ROLES)
                sel = vr[vr["Rol"].isin(roles_sel)]
                n_mail = sel["Entrega"].isin(["Electrónico", "Ambos"]).sum()
                n_print = sel["Entrega"].isin(["Impresión", "Ambos"]).sum()
                st.write(f"**{len(sel)}** constancias · 📧 {n_mail} por correo · 🖨️ {n_print} para imprimir")

                g1, g2 = st.columns(2)
                with g1:
                    st.subheader("🖨️ Impresión")
                    if st.button("Preparar archivos", disabled=sel.empty):
                        prog = st.progress(0.0)
                        files, to_print = {}, []
                        for i, (_, r) in enumerate(sel.iterrows(), 1):
                            p = certificate(cfg, r["Rol"], r["Nombre"])
                            files[filename_for(r["Rol"], r["Nombre"])] = p
                            if r["Entrega"] in ("Impresión", "Ambos"):
                                to_print.append(p)
                            prog.progress(i / len(sel))
                        st.session_state["zip"] = gen.zip_pdfs(files)
                        st.session_state["print_pdf"] = gen.merge_pdfs(to_print) if to_print else None
                    if st.session_state.get("zip"):
                        st.download_button("⬇️ ZIP con todos los PDF", st.session_state["zip"],
                                           "constancias.zip", "application/zip", width="stretch")
                    if st.session_state.get("print_pdf"):
                        st.download_button("⬇️ PDF único para imprimir (solo Impresión/Ambos)",
                                           st.session_state["print_pdf"], "constancias_para_imprimir.pdf",
                                           "application/pdf", width="stretch")
                with g2:
                    st.subheader("📧 Correo")
                    to_send = sel[sel["Entrega"].isin(["Electrónico", "Ambos"])
                                  & sel["Correo"].fillna("").map(mailer.is_valid_email)]
                    st.caption(f"Se enviarán {len(to_send)} correos (se omiten los de correo inválido).")
                    delay = st.number_input("Pausa entre correos (seg)", 0.0, 10.0, 1.0, 0.5,
                                            help="Evita que Gmail/Outlook bloqueen envíos masivos.")
                    confirm = st.checkbox("Confirmo que quiero enviar los correos")
                    if st.button("Enviar correos", type="primary",
                                 disabled=not confirm or to_send.empty):
                        if not cfg["smtp"]["user"] or not smtp_password():
                            st.error("Configura el correo en la pestaña 4 primero.")
                        else:
                            items = []
                            for _, r in to_send.iterrows():
                                subj, body = mail_fields(r)
                                items.append(dict(to=r["Correo"], subject=subj, body=body,
                                                  pdf=certificate(cfg, r["Rol"], r["Nombre"]),
                                                  filename=filename_for(r["Rol"], r["Nombre"])))
                            bar = st.progress(0.0)

                            def tick(i, n):
                                bar.progress(i / n)
                                if delay:
                                    time.sleep(delay)

                            res = mailer.send_many(cfg["smtp"], smtp_password(), items, tick)
                            st.session_state["send_log"] = pd.DataFrame(res)
                if "send_log" in st.session_state:
                    log = st.session_state["send_log"]
                    st.write(f"✅ {(log.status == 'Enviado').sum()} enviados · "
                             f"❌ {(log.status == 'Error').sum()} con error")
                    st.dataframe(log, width="stretch")

# ------------------------------------------------------------------ 4. Correo
with tab_mail:
    sm = cfg["smtp"]
    st.subheader("Cuenta de envío")
    st.caption("Gmail: usa una *contraseña de aplicación* (Cuenta de Google → Seguridad → Verificación en "
               "2 pasos → Contraseñas de aplicaciones). Outlook: smtp.office365.com, puerto 587.")
    a, b, c = st.columns(3)
    sm["host"] = a.text_input("Servidor SMTP", sm["host"])
    sm["port"] = b.number_input("Puerto", 1, 65535, int(sm["port"]))
    sm["user"] = c.text_input("Correo remitente", sm["user"])
    d, e = st.columns(2)
    sm["from_name"] = d.text_input("Nombre que verá el participante", sm["from_name"])
    st.session_state["smtp_pass"] = e.text_input(
        "Contraseña (no se guarda en disco)", type="password",
        value=st.session_state.get("smtp_pass", ""),
        help="También puedes definir la variable de entorno SMTP_PASSWORD.")

    st.subheader("Mensaje")
    st.caption("Variables disponibles: {nombre}  {rol}  {evento}")
    cfg["email"]["subject"] = st.text_input("Asunto", cfg["email"]["subject"])
    cfg["email"]["body"] = st.text_area("Cuerpo", cfg["email"]["body"], height=220)

    t1, t2 = st.columns(2)
    if t1.button("💾 Guardar configuración de correo", type="primary"):
        save_cfg(cfg)
        st.success("Guardado.")
    if t2.button("🔌 Probar conexión"):
        r = mailer.test_connection(sm, smtp_password())
        (st.success if r == "ok" else st.error)("Conexión correcta ✅" if r == "ok" else r)

save_cfg(cfg)
