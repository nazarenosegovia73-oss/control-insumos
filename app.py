import streamlit as st 
import pandas as pd
import re
import datetime
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Control de Taller e Inventarios", page_icon="🎨", layout="wide")

ID_SHEET = "1cJ6FH-lJWn52UzhMRAEhpIZ-FRcdfJNzwYtouAQE0CE"
RUTA_CREDENTIALES = "credenciales.json"

MESES_ESPANOL = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def obtener_cliente_gspread():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        if os.path.exists(RUTA_CREDENTIALES):
            creds = ServiceAccountCredentials.from_json_keyfile_name(RUTA_CREDENTIALES, scope)
        elif "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            if "private_key" in creds_dict:
                creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            st.error("No se encontró el archivo 'credenciales.json' ni la configuración de secrets.")
            return None
            
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

@st.cache_data(ttl=10)
def cargar_datos(nombre_hoja):
    try:
        client = obtener_cliente_gspread()
        if client is None:
            return pd.DataFrame()
        
        sheet = client.open_by_key(ID_SHEET)
        worksheet = sheet.worksheet(nombre_hoja)
        
        data = worksheet.get_all_values()
        if not data or len(data) <= 1:
            return pd.DataFrame()
            
        header = data[0]
        rows = data[1:]
        
        df = pd.DataFrame(rows, columns=header)
        return df
    except Exception as e:
        return pd.DataFrame()

def convertir_a_numero_precio(val):
    if pd.isna(val):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('$', '').strip()
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        if s.find(',') > s.find('.'):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    elif ',' in s:
        s = s.replace(',', '.')
    elif '.' in s and len(s.split('.')[-1]) == 3 and len(s.split('.')) > 2:
        s = s.replace('.', '')
    try:
        return float(s)
    except:
        return 0.0

def limpiar_tabla(df, mantener_dif=False):
    if df is None or df.empty:
        return df

    columnas_a_borrar = ['categoría', 'categoria', 'real', 'stok inicial', 'stock inicial']
    if not mantener_dif:
        columnas_a_borrar.append('dif')

    cols_a_eliminar = [c for c in df.columns if str(c).strip().lower() in columnas_a_borrar or 'unnamed' in str(c).lower()]
    df_limpio = df.drop(columns=cols_a_eliminar, errors='ignore').copy()

    for col in df_limpio.columns:
        col_lower = str(col).lower()
        if 'fecha' in col_lower:
            serie_str = df_limpio[col].astype(str).str.strip()
            serie_str = serie_str.str.replace('/', '-', regex=False)
            
            fechas_parsed = pd.to_datetime(serie_str, errors='coerce', dayfirst=True)
            
            mascara_nat = fechas_parsed.isna() & (serie_str != "") & (serie_str.str.lower() != "nan")
            if mascara_nat.any():
                for idx_f in df_limpio[mascara_nat].index:
                    val_str = str(df_limpio.loc[idx_f, col]).strip()
                    match = re.findall(r'(\d+)', val_str)
                    if len(match) >= 3:
                        try:
                            d, m, a = int(match[0]), int(match[1]), int(match[2])
                            if a < 100: a += 2000
                            fechas_parsed.loc[idx_f] = pd.Timestamp(year=a, month=m, day=d)
                        except:
                            pass
            
            fechas_parsed[fechas_parsed.dt.year < 2020] = pd.NaT
            df_limpio[col] = fechas_parsed
        elif any(k in col_lower for k in ['stock', 'cantidad', 'minimo', 'mínimo', 'dif']):
            df_limpio[col] = pd.to_numeric(df_limpio[col], errors='coerce').fillna(0).astype(int)
        elif any(k in col_lower for k in ['precio', 'costo', 'valor', 'unitario']):
            df_limpio[col] = df_limpio[col].apply(convertir_a_numero_precio)
        else:
            df_limpio[col] = df_limpio[col].fillna("").astype(str).str.strip()

    col_prod = next(
        (c for c in df_limpio.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo', 'descrip', 'articulo', 'artículo'])),
        df_limpio.columns[2] if len(df_limpio.columns) > 2 else df_limpio.columns[0]
    )

    df_limpio = df_limpio[
        df_limpio[col_prod].notna() & 
        (df_limpio[col_prod] != "") & 
        (df_limpio[col_prod] != "0") & 
        (df_limpio[col_prod].str.lower() != "nan")
    ].copy()

    return df_limpio

def aplicar_estilos(val):
    if str(val).strip().upper() == 'OK':
        return 'background-color: #d4edda; color: #155724; font-weight: bold;'
    elif str(val).strip().upper() == 'REPONER':
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
    return ''

def formatear_precio(val):
    return f"${val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# --- SELECTOR DE MUNDOS EN LA BARRA LATERAL ---

mundo_seleccionado = st.sidebar.radio(
    "Elegí con qué mundo querés trabajar:",
    options=["Insumos Generales", "Productos Glasurit", "Consolidado Global"],
    index=0
)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 Refrescar Datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

# ==========================================
# 🌍 LÓGICA DEL PRIMER MUNDO
# ==========================================
if mundo_seleccionado == "Insumos Generales":
    ID_SHEET_ACTUAL = ID_SHEET
    HOJA_INVENTARIO = "Inventario Insumos"
    HOJA_SALIDA = "salida"
    HOJA_INGRESO = "ingresos"
    HOJA_INDICADORES = "indicadores"
    TITULO_APP = "🛠️ Control de Insumos - Generales"
    PREFIX_KEYS = "m1"

elif mundo_seleccionado == "Productos Glasurit":
    ID_SHEET_ACTUAL = ID_SHEET
    HOJA_INVENTARIO = "inventario basf"
    HOJA_SALIDA = "salida basf"
    HOJA_INGRESO = "ingresos basf"
    HOJA_INDICADORES = "indicadores"
    TITULO_APP = "🎨 Control de Inventario - Productos Glasurit"
    PREFIX_KEYS = "m2"

else:  # Consolidado Global
    ID_SHEET_ACTUAL = ID_SHEET
    HOJA_INVENTARIO = ""
    HOJA_SALIDA = ""
    HOJA_INGRESO = ""
    HOJA_INDICADORES = "indicadores"
    TITULO_APP = "📊 Panel Consolidado Global del Taller"
    PREFIX_KEYS = "m3"

# --- CARGA DE DATOS SEGÚN EL INVENTARIO SELECCIONADO ---
if mundo_seleccionado == "Consolidado Global":
    df_inv_m1 = cargar_datos("Inventario Insumos")
    df_salida_m1 = cargar_datos("salida")
    df_ingreso_m1 = cargar_datos("ingresos")

    df_inv_m2 = cargar_datos("inventario basf")
    df_salida_m2 = cargar_datos("salida basf")
    df_ingreso_m2 = cargar_datos("ingresos basf")

    df_inventario_raw = pd.concat([df_inv_m1, df_inv_m2], ignore_index=True)
    df_salida_raw = pd.DataFrame()
    df_ingreso_raw = pd.DataFrame()
else:
    df_inventario_raw = cargar_datos(HOJA_INVENTARIO)
    df_salida_raw = cargar_datos(HOJA_SALIDA)
    df_ingreso_raw = cargar_datos(HOJA_INGRESO)

# --- BARRA LATERAL - CONSULTA RÁPIDA DE STOCK ---
st.sidebar.header("🔍 Consulta Rápida de Stock")

if df_inventario_raw is not None and not df_inventario_raw.empty:
    df_inv_sidebar = limpiar_tabla(df_inventario_raw)
    col_prod_inv = next((c for c in df_inv_sidebar.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo', 'descripcion'])), df_inv_sidebar.columns[1] if len(df_inv_sidebar.columns) > 1 else df_inv_sidebar.columns[0])
    col_stock_inv = next((c for c in df_inv_sidebar.columns if 'stock' in str(c).lower() or 'cantidad' in str(c).lower()), None)
    
    lista_productos = sorted([p for p in df_inv_sidebar[col_prod_inv].unique().tolist() if str(p).strip()])
    prod_seleccionado = st.sidebar.selectbox(
        "Buscar o seleccionar producto:", 
        options=lista_productos, 
        index=None, 
        placeholder="Escribí para buscar...",
        key=f"{PREFIX_KEYS}_busqueda_rapida"
    )
    
    if prod_seleccionado:
        cant_texto = "No especificado"
        if col_stock_inv:
            cant = df_inv_sidebar[df_inv_sidebar[col_prod_inv] == prod_seleccionado][col_stock_inv].values
            if len(cant) > 0:
                cant_texto = f"{cant[0]} unidades"

        fecha_texto = "Sin registros"
        proveedores_list = []

        if df_ingreso_raw is not None and not df_ingreso_raw.empty:
            df_ing_limpio_sb = limpiar_tabla(df_ingreso_raw)
            col_prod_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle', 'descripcion'])), None)
            col_fecha_ing = next((c for c in df_ing_limpio_sb.columns if 'fecha' in str(c).lower()), None)
            col_precio_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
            col_prov_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'local', 'vendedor'])), None)

            if col_prod_ing:
                historial_prod = df_ing_limpio_sb[df_ing_limpio_sb[col_prod_ing].astype(str).str.lower() == str(prod_seleccionado).lower()]
                
                if not historial_prod.empty:
                    if col_fecha_ing:
                        h_con_fecha = historial_prod.dropna(subset=[col_fecha_ing])
                        if not h_con_fecha.empty:
                            h_ordenada = h_con_fecha.sort_values(by=col_fecha_ing, ascending=True)
                            ultima_fecha = h_ordenada.iloc[-1][col_fecha_ing]
                            if pd.notna(ultima_fecha):
                                fecha_texto = pd.to_datetime(ultima_fecha).strftime('%d-%m-%Y')
                                
                    if col_prov_ing and col_precio_ing:
                        for prov, grp in historial_prod.groupby(col_prov_ing):
                            prov_str = str(prov).strip().title()
                            if prov_str and prov_str != "nan" and prov_str.lower() != "nan":
                                ult_p = grp.iloc[-1][col_precio_ing]
                                p_fmt = formatear_precio(ult_p) if pd.notna(ult_p) and ult_p > 0 else "S/D"
                                proveedores_list.append(f"{prov_str} ({p_fmt})")

                    prov_str = " • ".join(proveedores_list) if proveedores_list else "Sin registros"

        st.sidebar.success(
            f"📦 **{prod_seleccionado}**\n\n"
            f"• **Stock Disponible:** {cant_texto}\n"
            f"• **Última Compra:** {fecha_texto}\n"
            f"• **Proveedor(es) y Precio:**\n  • {prov_str}"
        )

# --- PESTAÑAS PRINCIPALES ---
st.title(TITULO_APP)

if mundo_seleccionado == "Consolidado Global":
    tab_reposicion, tab_indicadores, tab_graficos = st.tabs([
        "🛒 Reposición", 
        "📊 Indicadores", 
        "📈 Gráficos"
    ])
else:
    tab_ingreso, tab_salida, tab_reposicion, tab_inventario, tab_indicadores = st.tabs([
        "📥 Ingresos", 
        "📤 Salida", 
        "🛒 Reposición", 
        "📦 Inventario", 
        "📊 Indicadores"
    ])

if mundo_seleccionado != "Consolidado Global":
    key_ing_pend = f"{PREFIX_KEYS}_lista_ingresos_pendientes"
    key_sal_pend = f"{PREFIX_KEYS}_lista_salidas_pendientes"
    key_inv_pend = f"{PREFIX_KEYS}_lista_inventario_pendientes"

    if key_ing_pend not in st.session_state:
        st.session_state[key_ing_pend] = []
    if key_sal_pend not in st.session_state:
        st.session_state[key_sal_pend] = []
    if key_inv_pend not in st.session_state:
        st.session_state[key_inv_pend] = []

    # ==========================================
    # --- PESTAÑA INGRESOS ---
    # ==========================================
    with tab_ingreso:
        st.subheader("📝 Carga Rápida de Insumos (Ingresos)")
        
        opciones_proveedores = []
        if df_ingreso_raw is not None and not df_ingreso_raw.empty:
            col_prov_ing = next((c for c in df_ingreso_raw.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'donde', 'comprado'])), None)
            if col_prov_ing:
                provs_set = set()
                for p in df_ingreso_raw[col_prov_ing].dropna().astype(str).str.strip().unique().tolist():
                    p_str = p.strip().title()
                    if p_str and p_str != "0" and p_str.lower() != "nan":
                        provs_set.add(p_str)
                opciones_proveedores = sorted(list(provs_set))

        opciones_prods_col_c = []
        if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3:
            opciones_prods_col_c = sorted([p for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist() if p and p != "0" and p.lower() != "nan"])

        with st.form(f"form_agregar_item_ingreso_{PREFIX_KEYS}", clear_on_submit=True):
            col_prod, col_fecha = st.columns([3, 1])
            producto_ingresado = col_prod.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Escribí una letra para filtrar...", key=f"{PREFIX_KEYS}_prod_ing")
            fecha_ingreso = col_fecha.date_input("📅 Fecha de Compra *", value=datetime.date.today(), key=f"{PREFIX_KEYS}_fec_ing")

            col_cant, col_precio, col_prov = st.columns([1, 1, 2])
            cantidad_ingresada = col_cant.number_input("Cantidad *", min_value=1, value=1, step=1, key=f"{PREFIX_KEYS}_cant_ing")
            precio_ingresado = col_precio.number_input("Precio Unitario ($) *", min_value=0.0, value=0.0, step=100.0, key=f"{PREFIX_KEYS}_precio_ing")

            prov_seleccionado = col_prov.selectbox("Proveedor *", options=opciones_proveedores, index=None, placeholder="Seleccioná un proveedor...")
            nuevo_prov_escrito = st.text_input("➕ o escribí un nuevo proveedor aquí:", placeholder="Ej: Wurth Argentina", key=f"{PREFIX_KEYS}_nuevo_prov")
            proveedor_final = nuevo_prov_escrito.title() if nuevo_prov_escrito else (prov_seleccionado.title() if prov_seleccionado else "")

            observaciones_ingreso = st.text_input("💬 Observaciones:", placeholder="Ej: Factura A N° 000123 / Remito", key=f"{PREFIX_KEYS}_obs_ing")

            btn_agregar = st.form_submit_button("➕ Agregar a la Lista de Carga", type="secondary", use_container_width=True)

        if btn_agregar:
            errores = []
            if not producto_ingresado: errores.append("Producto / Detalle")
            if cantidad_ingresada < 1: errores.append("Cantidad")
            if precio_ingresado < 0: errores.append("Precio Unitario")
            if not proveedor_final: errores.append("Proveedor")

            if errores:
                st.error(f"⚠️ **Faltan campos:** {', '.join(errores)}")
            else:
                articulo_val, categoria_val, marca_val, medida_val = "", "", "", ""
                if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 5:
                    fila_match = df_inventario_raw[df_inventario_raw.iloc[:, 2].astype(str).str.strip() == str(producto_ingresado).strip()]
                    if not fila_match.empty:
                        articulo_val = str(fila_match.iloc[0, 0]) if not pd.isna(fila_match.iloc[0, 0]) else ""
                        categoria_val = str(fila_match.iloc[0, 1]) if not pd.isna(fila_match.iloc[0, 1]) else ""
                        marca_val = str(fila_match.iloc[0, 3]) if not pd.isna(fila_match.iloc[0, 3]) else ""
                        medida_val = str(fila_match.iloc[0, 4]) if not pd.isna(fila_match.iloc[0, 4]) else ""

                st.session_state[key_ing_pend].append({
                    "Articulo": articulo_val,
                    "Categoria": categoria_val,
                    "Producto": producto_ingresado,
                    "Marca": marca_val,
                    "Medida": medida_val,
                    "Cantidad": cantidad_ingresada,
                    "Fecha": fecha_ingreso.strftime("%d-%m-%Y"),
                    "Precio": precio_ingresado,
                    "Precio Total": precio_ingresado * cantidad_ingresada,
                    "Proveedor": proveedor_final,
                    "Observaciones": observaciones_ingreso
                })
                st.toast(f"✅ Agregado: {producto_ingresado}")
                st.rerun()

        if st.session_state[key_ing_pend]:
            st.markdown("---")
            st.subheader("🛒 Insumos Pendientes de Guardar (Ingresos)")
            df_pendientes = pd.DataFrame(st.session_state[key_ing_pend])
            df_editado = st.data_editor(df_pendientes, num_rows="dynamic", use_container_width=True, key=f"{PREFIX_KEYS}_editor_ing")
            col_guardar, col_limpiar = st.columns([3, 1])
            if col_guardar.button("💾 Guardar INGRESOS en Google Sheets", type="primary", use_container_width=True, key=f"{PREFIX_KEYS}_btn_save_ing"):
                client = obtener_cliente_gspread()
                if client:
                    try:
                        sheet_ingresos = client.open_by_key(ID_SHEET_ACTUAL).worksheet(HOJA_INGRESO)
                        col_c_values = sheet_ingresos.col_values(3)
                        primera_fila_vacia = len(col_c_values) + 1
                        filas_a_subir = df_editado.values.tolist()
                        rango_insertar = f"A{primera_fila_vacia}:K{primera_fila_vacia + len(filas_a_subir) - 1}"
                        sheet_ingresos.update(rango_insertar, filas_a_subir)
                        st.success(f"✅ ¡Se guardaron {len(filas_a_subir)} registros en Google Sheets!")
                        st.session_state[key_ing_pend] = []
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as err:
                        st.error(f"❌ Error al escribir en Google Sheets: {err}")
            if col_limpiar.button("🗑️ Cancelar Lista", use_container_width=True, key=f"{PREFIX_KEYS}_btn_cancel_ing"):
                st.session_state[key_ing_pend] = []
                st.rerun()

        st.markdown("---")
        st.subheader("📋 Historial Completo de Ingresos Registrados")
        if df_ingreso_raw is not None and not df_ingreso_raw.empty:
            df_ingreso_tabla = limpiar_tabla(df_ingreso_raw)
            if 'fecha' in df_ingreso_tabla.columns:
                df_ingreso_tabla['fecha'] = pd.to_datetime(df_ingreso_tabla['fecha'], errors='coerce').dt.strftime('%d-%m-%Y')
            st.dataframe(df_ingreso_tabla, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay ingresos registrados para este mundo.") 

    # ==========================================
    # --- PESTAÑA SALIDA ---
    # ==========================================
    with tab_salida:
        st.subheader("📄 Carga Rápida de Salida de Insumos")
        opciones_prods_col_c = []
        if df_inventario_raw is not None and not df_inventario_raw.empty:
            col_p = df_inventario_raw.columns[2] if len(df_inventario_raw.columns) > 2 else df_inventario_raw.columns[0]
            raw_prods = df_inventario_raw[col_p].dropna().astype(str).str.strip().unique()
            opciones_prods_col_c = sorted([p for p in raw_prods if p and p.lower() != 'nan'])
        
        opciones_tecnicos = []
        df_trabajo_salida = df_salida_raw

        if df_trabajo_salida is not None and not df_trabajo_salida.empty:
            cols_nombre = [c for c in df_trabajo_salida.columns if 'nombre' in str(c).lower()]
            col_nombre_tec = cols_nombre[0] if cols_nombre else df_trabajo_salida.columns[0]
            tecs_set = set()
            for t in df_trabajo_salida[col_nombre_tec].dropna().astype(str):
                t_str = t.strip().title()
                if t_str and t_str != "0" and t_str.lower() != "nan" and not t_str.replace('.', '', 1).isdigit():
                    tecs_set.add(t_str)
            opciones_tecnicos = sorted(list(tecs_set))

        with st.form(f"form_agregar_item_salida_{PREFIX_KEYS}", clear_on_submit=True):
            col_prod_s, col_fecha_s_form = st.columns([3, 1])
            producto_salida = col_prod_s.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Escribí una letra para filtrar...", key=f"{PREFIX_KEYS}_prod_sal")
            fecha_salida = col_fecha_s_form.date_input("📅 Fecha de Salida *", value=datetime.date.today(), key=f"{PREFIX_KEYS}_fec_sal")
            
            col_cant_s, col_tec_s_form = st.columns([1, 2])
            cantidad_salida = col_cant_s.number_input("🔢 Cantidad *", min_value=1, value=1, step=1, key=f"{PREFIX_KEYS}_cant_sal")
            tec_seleccionado = col_tec_s_form.selectbox("👷 Nombre / Técnico habitual *", options=opciones_tecnicos, index=None, placeholder="Seleccioná técnico...", key=f"{PREFIX_KEYS}_tec_sel")
            nuevo_tec_escrito = st.text_input("➕ O escribí un nuevo técnico / responsable:", placeholder="Ej: Roberto Gomez", key=f"{PREFIX_KEYS}_nuevo_tec").strip()
            tecnico_final = nuevo_tec_escrito.title() if nuevo_tec_escrito else (tec_seleccionado.title() if tec_seleccionado else "")

            observaciones_salida = st.text_input("📝 Observaciones (Columna L):", placeholder="Ej: Orden N° 1024 / Trabajo de pintura", key=f"{PREFIX_KEYS}_obs_sal").strip()

            btn_agregar_salida = st.form_submit_button("➕ Agregar Salida a la Lista", type="secondary", use_container_width=True)

        if btn_agregar_salida:
            errores_salida = []
            if not producto_salida: errores_salida.append("Producto / Detalle")
            if cantidad_salida <= 0: errores_salida.append("Cantidad")
            if not tecnico_final: errores_salida.append("Nombre / Técnico")
            
            if errores_salida:
                st.error(f"⚠️ **Faltan campos:** {', '.join(errores_salida)}")
            else:
                articulo_val = ""
                categoria_val = ""
                marca_val = ""
                medida_val = ""
                ubicacion_val = ""
                precio_automatico = 0.0
                proveedor_automatico = "Desconocido"
                
                if df_inventario_raw is not None and not df_inventario_raw.empty:
                    col_p_inv = next((c for c in df_inventario_raw.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo'])), df_inventario_raw.columns[0])
                    match_inv = df_inventario_raw[df_inventario_raw[col_p_inv].astype(str).str.strip().str.lower() == str(producto_salida).strip().lower()]
            
                    if not match_inv.empty:
                        col_art = next((c for c in df_inventario_raw.columns if 'articulo' in str(c).lower()), df_inventario_raw.columns[0])
                        col_ubic = next((c for c in df_inventario_raw.columns if 'ubicacion' in str(c).lower()), None)
                
                        articulo_val = str(match_inv.iloc[0][col_art]) if not pd.isna(match_inv.iloc[0][col_art]) else ""
                        ubicacion_val = str(match_inv.iloc[0][col_ubic]) if col_ubic and not pd.isna(match_inv.iloc[0][col_ubic]) else ""

                is_basf_mundo = "basf" in str(HOJA_SALIDA).lower() or "basf" in str(PREFIX_KEYS).lower()
                nombre_hoja_ingreso = "ingresos basf" if is_basf_mundo else "ingresos"

                df_ing_limp_s = pd.DataFrame()
                try:
                    client_ing = obtener_cliente_gspread()
                    if client_ing:
                        sheet_ing = client_ing.open_by_key(ID_SHEET_ACTUAL).worksheet(nombre_hoja_ingreso)
                        raw_data = sheet_ing.get_all_values()
                        if len(raw_data) > 1:
                            df_ing_limp_s = pd.DataFrame(raw_data[1:], columns=raw_data[0])
                        else:
                            df_ing_limp_s = pd.DataFrame(raw_data)
                except Exception:
                    if df_ingreso_raw is not None and not df_ingreso_raw.empty:
                        df_ing_limp_s = df_ingreso_raw.copy()

                if not df_ing_limp_s.empty:
                    df_ing_limp_s = limpiar_tabla(df_ing_limp_s)
                    
                    col_prod_ing_s = next((c for c in df_ing_limp_s.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle', 'articulo'])), None)
                    col_precio_ing_s = next((c for c in df_ing_limp_s.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
                    col_prov_ing_s = next((c for c in df_ing_limp_s.columns if any(k in str(c).lower() for k in ['proveedor', 'proovedor', 'local', 'vendedor'])), None)
                    
                    if col_prod_ing_s:
                        prod_buscado = str(producto_salida).strip().lower()
                        hist_prod = df_ing_limp_s[df_ing_limp_s[col_prod_ing_s].astype(str).str.strip().str.lower() == prod_buscado]
                        
                        if hist_prod.empty and articulo_val:
                            col_art_ing = next((c for c in df_ing_limp_s.columns if 'articulo' in str(c).lower()), None)
                            if col_art_ing:
                                hist_prod = df_ing_limp_s[df_ing_limp_s[col_art_ing].astype(str).str.strip().str.lower() == str(articulo_val).strip().lower()]

                        if not hist_prod.empty:
                            if col_precio_ing_s:
                                ult_precio_val = hist_prod.iloc[-1][col_precio_ing_s]
                                precio_automatico = convertir_a_numero_precio(ult_precio_val)
                            if col_prov_ing_s:
                                ult_prov_val = str(hist_prod.iloc[-1][col_prov_ing_s]).strip().title()
                                if ult_prov_val and ult_prov_val != "0" and ult_prov_val.lower() not in ["nan", "nat", "none"]:
                                    proveedor_automatico = ult_prov_val

                precio_total_calc = precio_automatico * cantidad_salida

                if "basf" in str(HOJA_SALIDA).lower() or "basf" in str(PREFIX_KEYS).lower():
                    datos_salida_dict = {
                        "articulo": articulo_val,
                        "Producto / Detalle": producto_salida,
                        "ubicacion": ubicacion_val,
                        "cantidad": cantidad_salida,
                        "fecha": fecha_salida.strftime("%d-%m-%Y"),
                        "nombre": tecnico_final,
                        "precio": precio_automatico,
                        "precio total": precio_total_calc,
                        "proovedor": proveedor_automatico,
                        "observaciones": observaciones_salida
                    }
                else:
                    datos_salida_dict = {
                        "articulo": articulo_val,
                        "Categoria": categoria_val,
                        "Producto / Detalle": producto_salida,
                        "Marca": marca_val,
                        "Medida / Variedad": medida_val,
                        "cantidad": cantidad_salida,
                        "fecha": fecha_salida.strftime("%d-%m-%Y"),
                        "nombre": tecnico_final,
                        "precio": precio_automatico,
                        "precio total": precio_total_calc,
                        "proveedor": proveedor_automatico,
                        "observaciones": observaciones_salida
                    }

                st.session_state[key_sal_pend].append(datos_salida_dict)
                st.toast(f"✅ Agregado a salidas: {producto_salida}")
                st.rerun()

        if st.session_state[key_sal_pend]:
            st.markdown("---")
            st.subheader("Salidas Pendientes de Guardar")
            df_pendientes_s = pd.DataFrame(st.session_state[key_sal_pend])
            df_editado_s = st.data_editor(df_pendientes_s, num_rows="dynamic", use_container_width=True, key=f"{PREFIX_KEYS}_editor_sal")
            col_guardar_s, col_limpiar_s = st.columns([3, 1])
            if col_guardar_s.button("💾 Guardar SALIDAS en Google Sheets", type="primary", use_container_width=True, key=f"{PREFIX_KEYS}_btn_save_sal"):
                client = obtener_cliente_gspread()
                if client:
                    try:
                        sheet_salida = client.open_by_key(ID_SHEET_ACTUAL).worksheet(HOJA_SALIDA)
                        col_c_values = sheet_salida.col_values(3)
                        primera_fila_vacia = len(col_c_values) + 1
                        filas_a_subir = df_editado_s.values.tolist()
                        rango_insertar = f"A{primera_fila_vacia}:L{primera_fila_vacia + len(filas_a_subir) - 1}"
                        sheet_salida.update(rango_insertar, filas_a_subir)
                        st.success(f"¡{len(filas_a_subir)} salidas guardadas en Google Sheets!")
                        st.session_state[key_sal_pend] = []
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as err:
                        st.error(f"❌ Error al escribir en Google Sheets: {err}")
            if col_limpiar_s.button("🗑️ Cancelar Lista (Salidas)", use_container_width=True, key=f"{PREFIX_KEYS}_btn_cancel_sal"):
                st.session_state[key_sal_pend] = []
                st.rerun()

        st.markdown("---")
        st.subheader("📋 Historial Completo de Salidas Registradas")
        if df_salida_raw is not None and not df_salida_raw.empty:
            df_salida_tabla = limpiar_tabla(df_salida_raw)
            if 'fecha' in df_salida_tabla.columns:
                df_salida_tabla['fecha'] = pd.to_datetime(df_salida_tabla['fecha'], errors='coerce').dt.strftime('%d-%m-%Y')
            st.dataframe(df_salida_tabla, use_container_width=True, hide_index=True)
        else:
            st.info("Aún no hay salidas registradas para este mundo.")

# ==========================================
# --- PESTAÑA REPOSICIÓN ---
# ==========================================
with tab_reposicion:
    st.subheader("🛒 Control y Gestión de Reposición")
    
    if df_inventario_raw is not None and not df_inventario_raw.empty:
        df_rep = limpiar_tabla(df_inventario_raw)
        
        col_f1, col_f2 = st.columns([2, 2])
        filtro_estado = col_f1.radio(
            "Visualizar:", 
            options=["🔴 Solo insumos a reponer", "📋 Ver todo el inventario"], 
            horizontal=True,
            key=f"{PREFIX_KEYS}_radio_rep"
        )
        
        cols_lower = {str(c).lower().strip(): c for c in df_rep.columns}
        col_estado_match = next((cols_lower[c] for c in cols_lower if 'estado' in c), None)
        col_stock_match = next((cols_lower[c] for c in cols_lower if ('stock' in c or 'actual' in c or 'cantidad' in c) and 'min' not in c and 'inicial' not in c), None)
        col_prod_match = next((cols_lower[c] for c in cols_lower if any(k in c for k in ['producto', 'detalle', 'insumo'])), df_rep.columns[1] if len(df_rep.columns) > 1 else df_rep.columns[0])

        if filtro_estado == "🔴 Solo insumos a reponer" and col_estado_match:
            df_rep_filtrado = df_rep[df_rep[col_estado_match].astype(str).str.strip().str.upper() == "REPONER"].copy()
        else:
            df_rep_filtrado = df_rep.copy()

        if col_estado_match:
            total_a_reponer = len(df_rep[df_rep[col_estado_match].astype(str).str.strip().str.upper() == "REPONER"])
            st.metric(label="Insumos que requieren reposición urgente", value=total_a_reponer)

        if not df_rep_filtrado.empty:
            st.markdown("---")
            st.dataframe(
                df_rep_filtrado.style.map(aplicar_estilos, subset=[col_estado_match] if col_estado_match else None),
                use_container_width=True, 
                hide_index=True
            )

            if col_estado_match and total_a_reponer > 0:
                st.markdown("### 📤 Generar Lista de Compras para Proveedor")
                if st.button("📋 Copiar / Ver resumen de faltantes para enviar", type="primary", key=f"{PREFIX_KEYS}_btn_faltantes"):
                    df_faltantes = df_rep[df_rep[col_estado_match].astype(str).str.strip().str.upper() == "REPONER"]
                    
                    resumen_texto = "*Hola! Necesito hacer un pedido de los siguientes insumos para el taller:*\n\n"
                    
                    mapa_minimos = {}
                    if len(df_inventario_raw.columns) >= 9:
                        for _, r_inv in df_inventario_raw.iterrows():
                            p_nom_raw = str(r_inv.iloc[2]).strip().lower()
                            p_min_raw = r_inv.iloc[8]
                            mapa_minimos[p_nom_raw] = p_min_raw

                    mapa_proveedores = {}
                    if df_ingreso_raw is not None and not df_ingreso_raw.empty:
                        df_ing_limp = limpiar_tabla(df_ingreso_raw)
                        c_prod_ing = next((c for c in df_ing_limp.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle'])), None)
                        c_prov_ing = next((c for c in df_ing_limp.columns if any(k in str(c).lower() for k in ['proveedor', 'proovedor', 'local', 'vendedor'])), None)
                        c_precio_ing = next((c for c in df_ing_limp.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
                        
                        if c_prod_ing and c_prov_ing:
                            for prod_val, grupo in df_ing_limp.groupby(df_ing_limp[c_prod_ing].astype(str).str.lower()):
                                provs_prod = []
                                for prov_val, subgrupo in grupo.groupby(c_prov_ing):
                                    p_nom = str(prov_val).strip().title()
                                    if p_nom and p_nom != "0" and p_nom.lower() != "nan":
                                        p_precio = subgrupo.iloc[-1][c_precio_ing] if c_precio_ing else 0.0
                                        precio_fmt = formatear_precio(p_precio) if (pd.notna(p_precio) and p_precio > 0) else "S/D"
                                        provs_prod.append(f"{p_nom} ({precio_fmt})")
                                mapa_proveedores[prod_val.strip()] = provs_prod

                    for idx, row in df_faltantes.iterrows():
                        p_nombre = str(row[col_prod_match]).strip()
                        p_stock = row[col_stock_match] if col_stock_match and col_stock_match in row else "0"
                        p_min = mapa_minimos.get(p_nombre.lower(), "0")
                        provs_encontrados = mapa_proveedores.get(p_nombre.lower(), [])
                        provs_texto = ", ".join(provs_encontrados) if provs_encontrados else "Sin proveedor registrado"
                        
                        resumen_texto += f"• *{p_nombre}* (Stock actual: {p_stock} | Mínimo: {p_min})\n  🏢 Proveedores habituales: {provs_texto}\n\n"
                    
                    st.text_area("Copiá este texto para pasarlo por WhatsApp o email:", value=resumen_texto, height=220, key=f"{PREFIX_KEYS}_textarea_faltantes")
        else:
            st.success("🎉 ¡Excelente noticia! No hay ningún insumo que requiera reposición en este momento.")

# ==========================================
# --- PESTAÑA INVENTARIO ---
# ==========================================
if mundo_seleccionado != "Consolidado Global":
    with tab_inventario:
        st.subheader("➕ Agregar Nuevo Artículo al Inventario")
        
        with st.form(f"form_nuevo_inventario_{PREFIX_KEYS}", clear_on_submit=True):
            is_basf_inv = "basf" in str(HOJA_INVENTARIO).lower()
            
            if is_basf_inv:
                col_art_inv, col_prod_inv = st.columns([1, 2])
                articulo_input = col_art_inv.text_input("🔢 Artículo *", placeholder="Ej: 3/9831766", key=f"{PREFIX_KEYS}_art_in").strip()
                producto_input = col_prod_inv.text_input("📦 Producto / Detalle *", placeholder="Ej: Lija al agua 220", key=f"{PREFIX_KEYS}_prod_in").strip()
            else:
                col_cat, col_prod_inv = st.columns([1, 2])
                categoria_input = col_cat.text_input("📁 Categoría *", placeholder="Ej: Pinturas, Lijas", key=f"{PREFIX_KEYS}_cat_in").strip()
                producto_input = col_prod_inv.text_input("📦 Producto / Detalle *", placeholder="Ej: Lija al agua 220", key=f"{PREFIX_KEYS}_prod_in").strip()

            col_marca, col_ubic = st.columns([2, 2])
            marca_input = col_marca.text_input("🏷️ Marca", placeholder="Ej: PPG, Norton, Wurth", key=f"{PREFIX_KEYS}_marca_in").strip()
            ubicacion_input = col_ubic.text_input("📍 Ubicación", placeholder="Ej: Depósito 1, Estante A", key=f"{PREFIX_KEYS}_ubic_in").strip()
            col_medida, col_stock_ini, col_min_inv = st.columns([2, 1, 1])
            opciones_medidas = ["bolsas", "cajas", "litros", "unidad", "lata", "bidon", "botella"]
            medida_input = col_medida.selectbox("📏 Medida / Unidad *", options=opciones_medidas, index=None, placeholder="Seleccionar medida...", key=f"{PREFIX_KEYS}_medida_in")
            stock_input = col_stock_ini.number_input("📦 Stock Inicial", min_value=0, step=1, value=0, key=f"{PREFIX_KEYS}_stock_in")
            min_input = col_min_inv.number_input("⚠️ Stock Mínimo", min_value=0, step=1, value=2, key=f"{PREFIX_KEYS}_min_in")

            btn_agregar_inv = st.form_submit_button("➕ Agregar Artículo a la Lista de Inventario", type="secondary", use_container_width=True)

        if btn_agregar_inv:
            errores_inv = []
            if is_basf_inv:
                if not articulo_input: 
                    errores_inv.append("Artículo")
            else:
                if not categoria_input: 
                    errores_inv.append("Categoría")
            
            if not producto_input: 
                errores_inv.append("Producto / Detalle")
            if not medida_input: 
                errores_inv.append("Medida / Unidad")

            opciones_prods_existentes = []
            if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3:
                for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist():
                    if p and p != "0" and p.lower() != "nan":
                        opciones_prods_existentes.append(p.lower())
            for pend in st.session_state[key_inv_pend]:
                if "producto" in pend and pend["producto"]:
                    opciones_prods_existentes.append(str(pend["producto"]).strip().lower())

            if producto_input and producto_input.lower() in set(opciones_prods_existentes):
                errores_inv.append(f"El producto '{producto_input}' ya existe en el inventario.")

            if errores_inv:
                st.error(f"⚠️ **Atención:** {', '.join(errores_inv)}")
            else:
                todos_los_codigos = []
                if df_inventario_raw is not None and not df_inventario_raw.empty:
                    col_cods = df_inventario_raw.iloc[:, 0].dropna().astype(str).tolist()
                    todos_los_codigos.extend([c.strip() for c in col_cods if c.strip() and c.strip() != "0" and c.strip().lower() != "nan"])
                for pend in st.session_state[key_inv_pend]:
                    if "articulo" in pend and pend["articulo"]:
                        todos_los_codigos.append(str(pend["articulo"]).strip())

                nuevo_codigo = "001-0001"
                if todos_los_codigos:
                    ultimo_cod = todos_los_codigos[-1]
                    numeros = re.findall(r'\d+', ultimo_cod)
                    if numeros:
                        num_int = int(numeros[-1])
                        nuevo_codigo = ultimo_cod.replace(numeros[-1], str(num_int + 1).zfill(len(numeros[-1])))
                    else:
                        nuevo_codigo = str(len(todos_los_codigos) + 1).zfill(3)

                st.session_state[key_inv_pend].append({
                    "articulo": articulo_input if is_basf_inv else nuevo_codigo,
                    "categoria": "BASF" if is_basf_inv else categoria_input,
                    "producto": producto_input,
                    "marca": marca_input,
                    "medida": medida_input,
                    "real": stock_input,
                    "stock_actual": stock_input,
                    "stock_minimo": min_input,
                    "ubicacion": ubicacion_input,
                    "estado": ""
                })

                st.toast(f"➕ Agregado al inventario pendiente: {producto_input}")
                st.rerun()

        if st.session_state[key_inv_pend]:
            st.markdown("---")
            st.subheader("🛒 Inventarios Pendientes de Guardar")
            df_pendientes_inv = pd.DataFrame(st.session_state[key_inv_pend])
            df_editado_inv = st.data_editor(df_pendientes_inv, num_rows="dynamic", use_container_width=True, key=f"{PREFIX_KEYS}_editor_inv")
            col_guardar_inv, col_limpiar_inv = st.columns([3, 1])
            
            if col_guardar_inv.button("💾 Guardar INVENTARIO en Google Sheets", type="primary", use_container_width=True, key=f"{PREFIX_KEYS}_btn_save_inv"):
                client = obtener_cliente_gspread()
                if client:
                    try:
                        sheet_inv = client.open_by_key(ID_SHEET_ACTUAL).worksheet(HOJA_INVENTARIO)
                        is_basf_saving = "basf" in str(HOJA_INVENTARIO).lower() or "basf" in sheet_inv.title.lower()
                        
                        col_a_valores = sheet_inv.col_values(1)
                        primera_fila_vacia = len(col_a_valores) + 1
                        cant_filas = len(df_editado_inv)
                        
                        if is_basf_saving:
                            bloque_A_G = []
                            bloque_H_K = []
                            
                            for i, row in df_editado_inv.iterrows():
                                fila_actual = primera_fila_vacia + len(bloque_H_K)
                                
                                articulo = row["articulo"]
                                categoria = row.get("categoria", "")
                                producto = row["producto"]
                                marca = row.get("marca", "")
                                medida = row.get("medida", "")
                                real = "" 
                                
                                formula_stock_actual = f"=SI.ERROR(SUMAR.SI('ingresos basf'!$A:$A; $A{fila_actual}; 'ingresos basf'!$F:$F) - SUMAR.SI('salida basf'!$A:$A; $A{fila_actual}; 'salida basf'!$D:$D); 0)"
                                bloque_A_G.append([articulo, categoria, producto, marca, medida, real, formula_stock_actual])
                                
                                formula_dif = f"=G{fila_actual}"
                                stock_min = row["stock_minimo"]
                                formula_estado = f'=SI(G{fila_actual}<=I{fila_actual}; "REPONER"; "OK")'
                                ubicacion = row.get("ubicacion", "")
                                bloque_H_K.append([formula_dif, stock_min, formula_estado, ubicacion])
                            
                            sheet_inv.update(f"A{primera_fila_vacia}:G{primera_fila_vacia + cant_filas - 1}", bloque_A_G, value_input_option="USER_ENTERED")
                            sheet_inv.update(f"H{primera_fila_vacia}:K{primera_fila_vacia + cant_filas - 1}", bloque_H_K, value_input_option="USER_ENTERED")
                        else:
                            bloque_A_G = df_editado_inv[["articulo", "categoria", "producto", "marca", "medida", "real", "stock_actual"]].values.tolist()
                            sheet_inv.update(f"A{primera_fila_vacia}:G{primera_fila_vacia + cant_filas - 1}", bloque_A_G)

                            bloque_H_I = df_editado_inv.apply(
                                lambda row: ["", row["stock_minimo"]], axis=1
                            ).values.tolist()
                            ubicaciones = df_editado_inv[["ubicacion"]].values.tolist()

                            sheet_inv.update(f"H{primera_fila_vacia}:I{primera_fila_vacia + cant_filas - 1}", bloque_H_I)
                            sheet_inv.update(f"K{primera_fila_vacia}:K{primera_fila_vacia + cant_filas - 1}", ubicaciones)
                
                        st.success(f"¡Se guardaron {cant_filas} artículos en Google Sheets!")
                        st.session_state[key_inv_pend] = []
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as err:
                        st.error(f"❌ Error al escribir en Google Sheets: {err}")

        st.markdown("---")
        st.subheader("📋 Tabla Completa de Inventario")
        if df_inventario_raw is not None and not df_inventario_raw.empty:
            df_inv_tabla = limpiar_tabla(df_inventario_raw, mantener_dif=True)
            st.dataframe(df_inv_tabla, use_container_width=True, hide_index=True)

# ==========================================
# --- PESTAÑA INDICADORES ---
# ==========================================
with tab_indicadores:
    if mundo_seleccionado == "Consolidado Global":
        st.subheader("📊 Panel Global de Indicadores y Costos por Paño")
        client_ind = obtener_cliente_gspread()
        lista_global = []
        if client_ind:
            try:
                sheet_w = client_ind.open_by_key(ID_SHEET_ACTUAL).worksheet("indicadores")
                filas = sheet_w.get_all_values()
                if len(filas) > 1:
                    for f in filas[1:]:
                        if len(f) >= 8 and f[0].strip():
                            periodo = f[0].strip()
                            try:
                                panos = int(float(f[1].replace(".", "").replace(",", "."))) if f[1] else 0
                                gasto_gen = convertir_a_numero_precio(f[2]) if len(f) > 2 and f[2] else 0.0
                                gasto_basf = convertir_a_numero_precio(f[3]) if len(f) > 3 and f[3] else 0.0
                                total_gastos = convertir_a_numero_precio(f[4]) if len(f) > 4 and f[4] else (gasto_gen + gasto_basf)
                                
                                if panos > 0 or total_gastos > 0:
                                    lista_global.append({
                                        "Período / Mes": periodo,
                                        "Paños Realizados": panos,
                                        "Insumos Generales ($)": gasto_gen,
                                        "Productos Glasurit ($)": gasto_basf,
                                        "Gasto Total ($)": total_gastos,
                                        "Costo por Paño ($)": (total_gastos / panos) if panos > 0 else 0.0,
                                        "Técnicos": int(float(f[6])) if len(f) > 6 and f[6].strip() else 10,
                                        "Días Hábiles": int(float(f[7])) if len(f) > 7 and f[7].strip() else 21,
                                        "orden_cronologico": int(''.join(filter(str.isdigit, periodo))) if any(char.isdigit() for char in periodo) else 0
                                    })
                            except:
                                pass
            except Exception as e:
                st.error(f"Error al leer indicadores globales: {e}")
        
        df_global = pd.DataFrame(lista_global)
        
        if not df_global.empty:
            st.markdown("---")
            st.subheader("🗓️ Período y Desglosé Estratégico")
            meses = df_global['Período / Mes'].tolist()
            
            nombres_meses = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 
                            7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
            mes_actual_str = f"{nombres_meses[datetime.datetime.now().month]} {datetime.datetime.now().year}"
            
            default_idx = meses.index(mes_actual_str) if mes_actual_str in meses else 0
            
            mes_sel = st.selectbox("Seleccioná el mes a analizar:", meses, index=default_idx, key="sel_mes")
            m = df_global[df_global['Período / Mes'] == mes_sel].iloc[0]

            p_res = m.get('Paños Realizados', 0)
            g_ins = m.get('Insumos Generales ($)', 0)
            g_glas = m.get('Productos Glasurit ($)', 0)
            g_tot = m.get('Gasto Total ($)', 0)
            costo_pano_mes = m.get('Costo por Paño ($)', 0)

            cl = {str(c).strip().lower(): m[c] for c in m.index}
            
            tec_val = next((v for k, v in cl.items() if 'tecnico' in k), 10)
            tec = int(tec_val) if pd.notna(tec_val) and str(tec_val).strip() != '' else 10
            
            dias_val = next((v for k, v in cl.items() if 'dia' in k or 'abil' in k), 21)
            dias = int(dias_val) if pd.notna(dias_val) and str(dias_val).strip() != '' else 21
            st.markdown("---")
            
            st.subheader(f"📊 KPIs del Taller — {mes_sel}")
            col_gk1, col_gk2, col_gk3 = st.columns(3)
            col_gk1.metric("GASTO TOTAL DEL MES", formatear_precio(g_tot))
            col_gk2.metric("PAÑOS REALIZADOS", f"{int(p_res):,}".replace(",", "."))
            col_gk3.metric("COSTO PROMEDIO X PAÑO", formatear_precio(costo_pano_mes))

            st.markdown("---")

            df_actual = df_global[df_global["Período / Mes"] == mes_sel]
            tec = int(df_actual["Técnicos"].values[0]) if not df_actual.empty else 10
            dias = int(df_actual["Días Hábiles"].values[0]) if not df_actual.empty else 21
            
            hoy = datetime.datetime.now()
            meses_es_dict = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 
                            7: "julio", 8: "agosto", 9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
            mes_actual_str = f"{meses_es_dict[hoy.month]} {hoy.year}"

            if mes_sel == mes_actual_str:
                inicio_mes = datetime.datetime(hoy.year, hoy.month, 1)
                dias_transcurridos = 0
                dia_cursor = inicio_mes
                while dia_cursor.date() <= hoy.date():
                    if dia_cursor.weekday() < 5: 
                        dias_transcurridos += 1
                    dia_cursor += datetime.timedelta(days=1)
                dias_efectivos = max(1, dias_transcurridos)
            else:
                dias_efectivos = dias
            
            p_ins = (g_ins / g_tot * 100) if g_tot > 0 else 0.0
            p_glas = (g_glas / g_tot * 100) if g_tot > 0 else 0.0
            c_diario = g_tot / dias_efectivos if dias_efectivos > 0 else 0
            p_prom = p_res / dias_efectivos if dias_efectivos > 0 else 0
            p_tec = p_prom / tec if tec > 0 else 0

            st.info(f"ℹ️ Cálculo para **{mes_sel}**: **{dias_efectivos}** días hábiles (efectivos) y **{tec}** técnicos.")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Participación", f"{p_ins:.1f}% / {p_glas:.1f}%")
            c2.metric("Costo Diario", formatear_precio(c_diario))
            c3.metric("Prod. Promedio", f"{p_prom:.1f} p/día")
            c4.metric(f"Por Técnico ({tec})", f"{p_tec:.1f} p/día")

            st.markdown("---")
            st.subheader("📋 Historial Consolidado por Mes")
            prods_dia, p_tecs = [], []
            df_tabla = df_global.copy()
            for _, row in df_tabla.iterrows():
                cl = {str(c).strip().lower(): row[c] for c in row.index}
                tec = int(next((v for k, v in cl.items() if 'tecnico' in k), 11))
                dias = int(next((v for k, v in cl.items() if 'dia' in k or 'abil' in k), 21))
                p_res = row['Paños Realizados']
                
                p_prom = p_res / dias if dias > 0 else 0
                p_tec = p_prom / tec if tec > 0 else 0
                
                prods_dia.append(f"{p_prom:.1f} p/día")
                p_tecs.append(f"{p_tec:.1f} p/día")

            df_tabla['Prod. Promedio'] = prods_dia
            df_tabla['Por Técnico'] = p_tecs
            
            df_global_display = df_tabla.sort_values(by="orden_cronologico", ascending=False).drop(columns=["orden_cronologico"]).copy()
            df_global_display["Insumos Generales ($)"] = df_global_display["Insumos Generales ($)"].apply(formatear_precio)
            df_global_display["Productos Glasurit ($)"] = df_global_display["Productos Glasurit ($)"].apply(formatear_precio)
            df_global_display["Gasto Total ($)"] = df_global_display["Gasto Total ($)"].apply(formatear_precio)
            df_global_display["Costo por Paño ($)"] = df_global_display["Costo por Paño ($)"].apply(formatear_precio)
            col_d1, col_d2 = st.columns(2)
            lista_meses_disp = df_global_display['Período / Mes'].tolist()
            with col_d1:
                mes_desde = st.selectbox("Desde el mes:", lista_meses_disp, index=max(0, len(lista_meses_disp)-6))
            with col_d2:
                mes_hasta = st.selectbox("Hasta el mes:", lista_meses_disp, index=len(lista_meses_disp)-1)

            idx_d, idx_h = lista_meses_disp.index(mes_desde), lista_meses_disp.index(mes_hasta)
            if idx_d <= idx_h:
                df_global_display = df_global_display[df_global_display['Período / Mes'].isin(lista_meses_disp[idx_d:idx_h+1])]
            
            st.dataframe(df_global_display, use_container_width=True, hide_index=True)
        else:
            st.info("No se encontraron registros en la hoja 'indicadores' de Google Sheets para mostrar en el consolidado.")
        
        st.markdown("---")
        st.subheader("📊 Consumo e Inversión por Insumo y por Paño")

        # --- Carga independiente para el filtro de consumo por insumo ---
   # --- Carga independiente y combinada (Salida + Salida BASF para Consolidado Global) ---
    df_salida_local = pd.DataFrame()
    if 'client_ind' in locals() and client_ind is not None:
        try:
            # Definir qué solapas leer según el mundo seleccionado
            mundo_str = str(mundo_seleccionado).lower() if 'mundo_seleccionado' in locals() else ""
            
            if "global" in mundo_str:
                hojas_a_leer = ["salida", "salida basf"]
            elif "basf" in mundo_str:
                hojas_a_leer = ["salida basf"]
            else:
                hojas_a_leer = ["salida"]
                
            dfs_temporales = []
            for hoja in hojas_a_leer:
                try:
                    sheet_ind = client_ind.open_by_key(ID_SHEET_ACTUAL).worksheet(hoja)
                    filas = sheet_ind.get_all_values()
                    if len(filas) > 1:
                        df_t = pd.DataFrame(filas[1:], columns=filas[0])
                        dfs_temporales.append(df_t)
                except Exception:
                    pass
            
            if dfs_temporales:
                # Unir las tablas de ambas solapas en una sola
                df_temp_raw = pd.concat(dfs_temporales, ignore_index=True)
                df_salida_local = limpiar_tabla(df_temp_raw)
        except Exception:
            pass

        if not df_salida_local.empty:
            df_ins = df_salida_local.copy()
            cols_map = {str(c).strip().lower(): c for c in df_ins.columns}
            col_prod = next((cols_map[c] for c in cols_map if 'producto' in c or 'insumo' in c), None)
            col_cant = next((cols_map[c] for c in cols_map if 'cantidad' in c or 'cant' in c), None)
            col_fecha = next((cols_map[c] for c in cols_map if 'fecha' in c), None)
            
            if col_prod and col_cant:
                df_ins[col_cant] = pd.to_numeric(df_ins[col_cant], errors='coerce').fillna(0)
                
                # 1. Preparar fechas y meses globales para los selectores de rango
                if col_fecha:
                    df_ins['fecha_dt'] = pd.to_datetime(df_ins[col_fecha], errors='coerce')
                    meses_map_es = {
                        1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
                        5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
                        9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
                    }
                    def formatear_mes_anio(dt):
                        if pd.isna(dt):
                            return "Sin Fecha"
                        return f"{meses_map_es.get(dt.month, '')} {dt.year}"
                    
                    df_ins['mes_anio'] = df_ins['fecha_dt'].apply(formatear_mes_anio)
                    
                    # Obtener TODOS los meses disponibles en el sistema
                    meses_disp = df_ins.sort_values('fecha_dt')['mes_anio'].dropna().unique().tolist()
                    
                    if meses_disp:
                        st.markdown("#### 🔍 Filtrar por rango de meses:")
                        col_f1, col_f2 = st.columns(2)
                        with col_f1:
                            m_desde = st.selectbox("Desde el mes:", meses_disp, index=0, key="audit_mes_desde")
                        with col_f2:
                            m_hasta = st.selectbox("Hasta el mes:", meses_disp, index=len(meses_disp)-1, key="audit_mes_hasta")
                        
                        # Aplicar filtro de rango de meses a la tabla general
                        try:
                            idx_d = meses_disp.index(m_desde)
                            idx_h = meses_disp.index(m_hasta)
                            if idx_d <= idx_h:
                                meses_seleccionados = meses_disp[idx_d:idx_h+1]
                                df_ins = df_ins[df_ins['mes_anio'].isin(meses_seleccionados)]
                        except Exception:
                            pass

                # 2. Selector de insumos basado en el período ya filtrado
                lista_insumos = sorted(df_ins[col_prod].dropna().unique().tolist())
                if lista_insumos:
                    insumo_elegido = st.selectbox("Seleccioná el insumo a auditar:", lista_insumos, key="sel_auditoria_insumo_global")
                    
                    df_filtrado_ins = df_ins[df_ins[col_prod] == insumo_elegido]
                    
                    st.markdown(f"### 📊 Auditoría de Consumo: **{insumo_elegido}**")
                    
                    # 3. Mostrar métricas agrupadas por mes dentro del rango seleccionado
                    if not df_filtrado_ins.empty and 'mes_anio' in df_filtrado_ins.columns:
                        resumen_mensual = df_filtrado_ins.groupby('mes_anio').agg(
                            consumo_mensual=(col_cant, 'sum'),
                            movimientos_totales=(col_cant, 'count')
                        ).reset_index()
                        
                        # Extraer paños reales de la tabla superior de indicadores
                        panos_por_mes = {}
                        if 'df_global_display' in locals() and df_global_display is not None and not df_global_display.empty:
                            try:
                                for _, row_g in df_global_display.iterrows():
                                    p_mes = str(row_g.get('Período / Mes', '')).strip().lower()
                                    p_cant = row_g.get('Paños Realizados', 0)
                                    panos_por_mes[p_mes] = p_cant
                            except Exception:
                                pass

                        for _, row in resumen_mensual.iterrows():
                            mes_str = str(row['mes_anio']).strip().lower()
                            consumo_total = row['consumo_mensual']
                            panos_reales = panos_por_mes.get(mes_str, 0)
                            if panos_reales == 0:
                                panos_reales = row['movimientos_totales']
                            
                            promedio_paño = consumo_total / panos_reales if panos_reales > 0 else 0
                            
                            with st.container():
                                st.markdown(f"##### 📅 Período: **{str(row['mes_anio']).capitalize()}**")
                                col_m1, col_m2, col_m3 = st.columns(3)
                                with col_m1:
                                    st.metric("Consumo Mensual", f"{consumo_total:,.2f} un.")
                                with col_m2:
                                    st.metric("Paños Realizados", f"{panos_reales}")
                                with col_m3:
                                    st.metric("Consumo por Paño", f"{promedio_paño:,.2f} un.")
                                st.markdown("---")
                    else:
                        st.info("No hay movimientos para este insumo en el rango de meses seleccionado.")
                    
                    # 4. Tabla detallada compacta
                    with st.expander("🔍 Ver tabla de movimientos detallados"):
                        st.dataframe(
                            df_filtrado_ins.drop(columns=['fecha_dt', 'mes_anio'], errors='ignore'), 
                            use_container_width=True, 
                            hide_index=True, 
                            height=220
                        )
                else:
                    st.warning("No hay insumos disponibles para el rango de fechas seleccionado.")
                    
            else:
                st.warning("No se pudieron detectar automáticamente las columnas de 'Producto' o 'Cantidad' en la tabla de salidas.")
        else:
            st.info("No hay datos de salidas cargados para procesar el rendimiento por insumo.")
    else:   
        st.subheader(f"📊 Panel de Control y Costos por Paño - {mundo_seleccionado}")
        df_salida_limp = limpiar_tabla(df_salida_raw) if df_salida_raw is not None and not df_salida_raw.empty else pd.DataFrame()
        dict_panos_sheet = {}
        client_ind = obtener_cliente_gspread()
        if client_ind:
            try:
                sheet_ind_obj = client_ind.open_by_key(ID_SHEET_ACTUAL).worksheet(HOJA_INDICADORES)
                filas_ind = sheet_ind_obj.get_all_values()
                if filas_ind:
                    mes_map_dict = {
                        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
                        "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
                        "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                    }
                    for f in filas_ind[1:]:
                        if len(f) >= 2:
                            m_txt = str(f[0]).strip().lower()
                            p_txt = str(f[1]).strip()
                                
                            mes_val = None
                            for m_nombre, m_num in mes_map_dict.items():
                                if m_nombre in m_txt:
                                    mes_val = m_num
                                    break
                                
                            match_anio = re.search(r'(20\d{2})', m_txt)
                            if mes_val and match_anio:
                                anio_val = int(match_anio.group(1))
                                try:
                                    val_p = int(float(p_txt.replace(",", "."))) if p_txt else 0
                                    dict_panos_sheet[(anio_val, mes_val)] = val_p
                                except:
                                    pass
            except Exception:
                pass
                
        lista_meses_nombres = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        meses_a_procesar = set(dict_panos_sheet.keys())
        
        if not df_salida_limp.empty:
            col_fecha_sal = next((c for c in df_salida_limp.columns if 'fecha' in str(c).lower()), None)
            if col_fecha_sal:
                df_salida_limp['dt_real'] = pd.to_datetime(df_salida_limp[col_fecha_sal], errors='coerce', dayfirst=True)
                for _, r in df_salida_limp.dropna(subset=['dt_real']).iterrows():
                    meses_a_procesar.add((int(r['dt_real'].year), int(r['dt_real'].month)))
                    
        resumen_meses = []
        for anio_val, mes_num in sorted(list(meses_a_procesar), key=lambda x: (x[0], x[1]), reverse=True):
            nombre_m = lista_meses_nombres[mes_num - 1]
            nombre_periodo = f"{nombre_m.capitalize()} {int(anio_val)}"
            
            costo_mes = 0.0
            if not df_salida_limp.empty:
                col_fecha_sal = next((c for c in df_salida_limp.columns if 'fecha' in str(c).lower()), None)
                col_total_sal = next((c for c in df_salida_limp.columns if 'precio_total' in str(c).lower() or 'total' in str(c).lower()), None)
                if col_fecha_sal and col_total_sal:
                    sub_df = df_salida_limp[
                        (df_salida_limp['dt_real'].dt.year == anio_val) & 
                        (df_salida_limp['dt_real'].dt.month == mes_num)
                    ]
                    costo_mes = sub_df[col_total_sal].apply(convertir_a_numero_precio).sum()
                    
            panos_mes = dict_panos_sheet.get((anio_val, mes_num), 0)
            
            if costo_mes > 0 or panos_mes > 0:
                resumen_meses.append({
                    "Período / Mes": nombre_periodo,
                    "Consumo Insumos ($)": costo_mes,
                    "Paños Realizados": panos_mes,
                    "Costo por Paño ($)": (costo_mes / panos_mes) if panos_mes > 0 else 0.0,
                    "orden_cronologico": int(anio_val) * 100 + int(mes_num)
                })

        if resumen_meses:
            df_resumen = pd.DataFrame(resumen_meses).sort_values(by="orden_cronologico", ascending=False)
            total_consumo = df_resumen["Consumo Insumos ($)"].sum()
            total_panos = int(df_resumen["Paños Realizados"].sum())
            costo_promedio = (total_consumo / total_panos) if total_panos > 0 else 0.0
        else:
            df_resumen = pd.DataFrame()
            total_consumo = 0.0
            total_panos = 0
            costo_promedio = 0.0
            
        if not df_resumen.empty:
            st.markdown("---")
            
        st.markdown("### 📋 Resumen Histórico (Meses con Movimiento)")

        st.markdown("📅 **Período de Análisis (para KPIs de Costos y Paños):**")
        opciones_periodo = ["Todos (Histórico con Datos)"] + df_resumen["Período / Mes"].tolist() if not df_resumen.empty else ["Todos (Histórico con Datos)"]
        periodo_sel_kpi = st.selectbox("", options=opciones_periodo, key=f"{PREFIX_KEYS}_kpi_periodo", label_visibility="collapsed")

        if periodo_sel_kpi == "Todos (Histórico con Datos)":
            df_kpi_filtrado = df_resumen
        else:
            df_kpi_filtrado = df_resumen[df_resumen["Período / Mes"] == periodo_sel_kpi]

        total_consumo_kpi = df_kpi_filtrado["Consumo Insumos ($)"].sum() if not df_kpi_filtrado.empty else 0
        total_panos_kpi = df_kpi_filtrado["Paños Realizados"].sum() if not df_kpi_filtrado.empty else 0
        costo_prom_kpi = (total_consumo_kpi / total_panos_kpi) if total_panos_kpi > 0 else 0

        st.subheader("📈 Indicadores Globales de Producción y Costos")
        col_k1, col_k2, col_k3 = st.columns(3)
        with col_k1:
            st.metric("CONSUMO DE INS. (REGISTRADO)", formatear_precio(total_consumo_kpi))
        with col_k2:
            st.metric("PAÑOS REALIZADOS", f"{total_panos_kpi:,}".replace(",", "."))
        with col_k3:
            st.metric("COSTO PROMEDIO X PAÑO", formatear_precio(costo_prom_kpi))

        st.markdown("---")

        if not df_resumen.empty:
            df_resumen_display = df_resumen.sort_values(by="orden_cronologico", ascending=False).head(6).drop(columns=["orden_cronologico"]).copy()
            df_resumen_display["Consumo Insumos ($)"] = df_resumen_display["Consumo Insumos ($)"].apply(formatear_precio)
            df_resumen_display["Costo por Paño ($)"] = df_resumen_display["Costo por Paño ($)"].apply(formatear_precio)
            st.dataframe(df_resumen_display, use_container_width=True, hide_index=True)
            
            if "glasurit" in str(mundo_seleccionado).lower():
                columna_destino = 4  
                label_mundo = "Productos Glasurit"
            else:
                columna_destino = 3  
                label_mundo = "Insumos Generales"

            if st.button(f"📤 Guardar Costos {label_mundo} en Google Sheets"):
                client_write = obtener_cliente_gspread()
                if client_write:
                    try:
                        sheet_w = client_write.open_by_key(ID_SHEET_ACTUAL).worksheet(HOJA_INDICADORES)
                        filas_hoja = sheet_w.get_all_values()
                        
                        actualizados = 0
                        for item in resumen_meses:
                            nombre_periodo_app = item["Período / Mes"]
                            gasto_app = item["Consumo Insumos ($)"]
                            mes_str_app = nombre_periodo_app.split()[0].lower()
                            
                            for idx, fila in enumerate(filas_hoja[1:], start=2):
                                if len(fila) > 0 and mes_str_app in str(fila[0]).lower():
                                    sheet_w.update_cell(idx, columna_destino, gasto_app)
                                    actualizados += 1
                                    break
                                    
                        st.success(f"¡Se actualizaron {actualizados} registros de {label_mundo} en Google Sheets!")
                    except Exception as e:
                        st.error(f"Error al escribir en Google Sheets: {e}")
                else:
                    st.warning("No se pudo conectar con Google Sheets.")
        else:
            st.info("Todavía no hay registros con consumos o paños cargados para mostrar en el histórico.")

        st.markdown("---")
        st.subheader("🏆 Análisis y Rankings del Taller")

        lista_opciones_str = df_resumen["Período / Mes"].tolist() if not df_resumen.empty else []
        opciones_ranking = ["Histórico Completo (Acumulado)"] + lista_opciones_str
        periodo_ranking_sel = st.selectbox("📅 Filtrar Rankings por Período:", options=opciones_ranking, index=0, key=f"{PREFIX_KEYS}_sel_ranking")

        df_salida_para_ranking = df_salida_limp.copy()
        if periodo_ranking_sel != "Histórico Completo (Acumulado)" and not df_salida_para_ranking.empty:
            partes_rk = periodo_ranking_sel.split()
            mes_str_rk, anio_str_rk = partes_rk[0], int(partes_rk[1])
            mes_num_rk = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str_rk.lower()][0]
            if 'dt_real' in df_salida_para_ranking.columns:
                df_salida_para_ranking = df_salida_para_ranking[
                    (df_salida_para_ranking['dt_real'].dt.year == anio_str_rk) & 
                    (df_salida_para_ranking['dt_real'].dt.month == mes_num_rk)
                ]

        col_top1, col_top2 = st.columns(2)

        with col_top1:
            st.markdown(f"#### 🔥 Top 5 Insumos con Mayor Costo ({periodo_ranking_sel})")
            if not df_salida_para_ranking.empty:
                c_prod_s = next((c for c in df_salida_para_ranking.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo'])), None)
                c_cant_s = next((c for c in df_salida_para_ranking.columns if 'cantidad' in str(c).lower()), None)
                c_tot_s = next((c for c in df_salida_para_ranking.columns if 'precio_total' in str(c).lower() or 'total' in str(c).lower()), None)

                if c_prod_s and c_cant_s:
                    df_salida_para_ranking['cant_num'] = df_salida_para_ranking[c_cant_s].apply(convertir_a_numero_precio)
                    df_salida_para_ranking['tot_num'] = df_salida_para_ranking[c_tot_s].apply(convertir_a_numero_precio) if c_tot_s else 0.0

                    top_insumos = df_salida_para_ranking.groupby(c_prod_s).agg({
                        'cant_num': 'sum',
                        'tot_num': 'sum'
                    }).reset_index().sort_values(by='tot_num', ascending=False).head(5)

                    top_insumos.columns = ["Producto / Insumo", "Cantidad Total", "Gasto Total ($)"]
                    top_insumos["Gasto Total ($)"] = top_insumos["Gasto Total ($)"].apply(formatear_precio)
                    st.dataframe(top_insumos, use_container_width=True, hide_index=True)
                else:
                    st.info("No se encontraron columnas de producto/cantidad en salidas.")
            else:
                st.info("No hay datos de salidas registrados para este período.")

        with col_top2:
            st.markdown(f"#### 👷 Top Técnicos / Responsables ({periodo_ranking_sel})")
            if not df_salida_para_ranking.empty:
                c_tec_s = next((c for c in df_salida_para_ranking.columns if any(k in str(c).lower() for k in ['nombre', 'tecnico', 'responsable'])), None)
                if c_tec_s and c_cant_s:
                    top_tecnicos = df_salida_para_ranking.groupby(c_tec_s).agg({
                        'cant_num': 'sum',
                        'tot_num': 'sum'
                    }).reset_index().sort_values(by='tot_num', ascending=False).head(5)

                    top_tecnicos.columns = ["Técnico / Responsable", "Unidades Retiradas", "Costo Asignado ($)"]
                    top_tecnicos["Costo Asignado ($)"] = top_tecnicos["Costo Asignado ($)"].apply(formatear_precio)
                    st.dataframe(top_tecnicos, use_container_width=True, hide_index=True)
                else:
                    st.info("No se encontró la columna de técnico/nombre en salidas.")
            else:
                st.info("No hay datos de salidas registrados para este período.")

        st.markdown("---")
        st.subheader("🔎 Consulta Histórica Detallada de Ingresos (Por Proveedor)")
        
        tipo_consulta_ing = st.radio(
            "Seleccioná el modo de consulta (Ingresos):",
            options=["🏢 Ver por Proveedor (Con filtros opcionales de Período y Producto)", "📦 Ver por Producto / Insumo (Con filtro opcional de Período)"],
            horizontal=True,
            key=f"{PREFIX_KEYS}_radio_con_ing"
        )

        if df_ingreso_raw is not None and not df_ingreso_raw.empty:
            df_ing_historial = limpiar_tabla(df_ingreso_raw)
            
            col_prov_h = next((c for c in df_ing_historial.columns if any(k in str(c).lower() for k in ['proveedor', 'proovedor', 'local', 'vendedor'])), None)
            col_prod_ing_h = next((c for c in df_ing_historial.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo'])), df_ing_historial.columns[2] if len(df_ing_historial.columns) > 2 else df_ing_historial.columns[0])
            col_cant_ing_h = next((c for c in df_ing_historial.columns if 'cantidad' in str(c).lower()), None)
            col_fecha_ing_h = next((c for c in df_ing_historial.columns if 'fecha' in str(c).lower()), None)

            periodos_ing_disp = ["[ Todos los períodos (Histórico completo) ]"]
            if col_fecha_ing_h:
                df_ing_historial['dt_aux_ing'] = pd.to_datetime(df_ing_historial[col_fecha_ing_h], errors='coerce', dayfirst=True)
                pares_aniomes_ing = df_ing_historial['dt_aux_ing'].dropna().apply(lambda x: (x.year, x.month)).unique()
                pares_ordenados_ing = sorted(list(pares_aniomes_ing), reverse=True)
                for a, m in pares_ordenados_ing:
                    m_nombre = MESES_ESPANOL.get(m, "")
                    if m_nombre:
                        periodos_ing_disp.append(f"{m_nombre} {a}")

            if "Proveedor" in tipo_consulta_ing and col_prov_h and col_prod_ing_h:
                lista_proveedores = sorted([p for p in df_ing_historial[col_prov_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                prov_elegido = st.selectbox("Seleccionar Proveedor:", options=lista_proveedores, index=None, placeholder="Escribí o seleccioná un proveedor...", key=f"{PREFIX_KEYS}_sel_prov")
                
                if prov_elegido:
                    df_prov_filtrado = df_ing_historial[df_ing_historial[col_prov_h].astype(str).str.lower() == prov_elegido.lower()].copy()
                    
                    periodo_elegido_ing = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_ing_disp, key=f"{PREFIX_KEYS}_sel_per_prov")
                    
                    if periodo_elegido_ing != "[ Todos los períodos (Histórico completo) ]":
                        partes = periodo_elegido_ing.split()
                        mes_str, anio_str = partes[0], int(partes[1])
                        mes_num_sel = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str.lower()][0]
                        df_prov_filtrado = df_prov_filtrado[(df_prov_filtrado['dt_aux_ing'].dt.year == anio_str) & (df_prov_filtrado['dt_aux_ing'].dt.month == mes_num_sel)]

                    lista_prods_prov = sorted([p for p in df_prov_filtrado[col_prod_ing_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                    prod_esp_prov = st.selectbox("📦 Filtrar por un producto específico (Opcional):", options=["[ Todos los productos ]"] + lista_prods_prov, index=0, key=f"{PREFIX_KEYS}_sel_prod_prov")

                    if prod_esp_prov != "[ Todos los productos ]":
                        df_prov_filtrado = df_prov_filtrado[df_prov_filtrado[col_prod_ing_h].astype(str).str.lower() == prod_esp_prov.lower()]

                    total_uni_prov = int(df_prov_filtrado[col_cant_ing_h].apply(convertir_a_numero_precio).sum()) if col_cant_ing_h else len(df_prov_filtrado)
                    
                    if col_fecha_ing_h and 'dt_aux_ing' in df_prov_filtrado.columns:
                        df_prov_filtrado[col_fecha_ing_h] = df_prov_filtrado['dt_aux_ing'].dt.strftime('%d-%m-%Y')

                    st.success(f"🏢 **{prov_elegido}** entregó un total de **{total_uni_prov} unidades** según los filtros aplicados.")
                    st.dataframe(df_prov_filtrado.drop(columns=['dt_aux_ing'], errors='ignore'), use_container_width=True, hide_index=True)
                else:
                    st.info("👆 Seleccioná un proveedor para ver su historial completo de entregas.")

            elif "Producto" in tipo_consulta_ing and col_prod_ing_h:
                lista_productos_ing = sorted([p for p in df_ing_historial[col_prod_ing_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                prod_ing_elegido = st.selectbox("Seleccionar Producto / Insumo (Ingresos):", options=lista_productos_ing, index=None, placeholder="Escribí o seleccioná un producto...", key=f"{PREFIX_KEYS}_sel_prod_ing_hist")
                
                if prod_ing_elegido:
                    df_prod_ing_filtrado = df_ing_historial[df_ing_historial[col_prod_ing_h].astype(str).str.lower() == prod_ing_elegido.lower()].copy()
                    
                    periodo_elegido_ing_p = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_ing_disp, key=f"{PREFIX_KEYS}_sel_per_prod_ing")
                    
                    if periodo_elegido_ing_p != "[ Todos los períodos (Histórico completo) ]":
                        partes_p = periodo_elegido_ing_p.split()
                        mes_str_p, anio_str_p = partes_p[0], int(partes_p[1])
                        mes_num_sel_p = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str_p.lower()][0]
                        df_prod_ing_filtrado = df_prod_ing_filtrado[(df_prod_ing_filtrado['dt_aux_ing'].dt.year == anio_str_p) & (df_prod_ing_filtrado['dt_aux_ing'].dt.month == mes_num_sel_p)]

                    total_uni_prod_ing = int(df_prod_ing_filtrado[col_cant_ing_h].apply(convertir_a_numero_precio).sum()) if col_cant_ing_h else len(df_prod_ing_filtrado)
                    
                    if col_fecha_ing_h and 'dt_aux_ing' in df_prod_ing_filtrado.columns:
                        df_prod_ing_filtrado[col_fecha_ing_h] = df_prod_ing_filtrado['dt_aux_ing'].dt.strftime('%d-%m-%Y')

                    st.success(f"📦 Del producto **{prod_ing_elegido}** se ingresaron **{total_uni_prod_ing} unidades** en el período seleccionado.")
                    st.dataframe(df_prod_ing_filtrado.drop(columns=['dt_aux_ing'], errors='ignore'), use_container_width=True, hide_index=True)
                else:
                    st.info("👆 Seleccioná un producto para ver el detalle histórico de sus ingresos.")

        st.markdown("---")
        st.subheader("🔎 Consulta Histórica Detallada de Salidas (Por Técnico)")
        
        tipo_consulta = st.radio(
            "Seleccioná el modo de consulta (Salidas):",
            options=["👷 Ver por Técnico (Con filtros opcionales de Período y Producto)", "📦 Ver por Producto / Insumo (Con filtro opcional de Período)"],
            horizontal=True,
            key=f"{PREFIX_KEYS}_radio_con_sal"
        )

        if df_salida_raw is not None and not df_salida_raw.empty:
            df_historial_total = limpiar_tabla(df_salida_raw)
            
            col_tec_h = next((c for c in df_historial_total.columns if any(k in str(c).lower() for k in ['nombre', 'tecnico', 'responsable'])), None)
            col_prod_h = next((c for c in df_historial_total.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo'])), df_historial_total.columns[2] if len(df_historial_total.columns) > 2 else df_historial_total.columns[0])
            col_cant_h = next((c for c in df_historial_total.columns if 'cantidad' in str(c).lower()), None)
            col_fecha_h = next((c for c in df_historial_total.columns if 'fecha' in str(c).lower()), None)

            periodos_disponibles_consulta = ["[ Todos los períodos (Histórico completo) ]"]
            if col_fecha_h:
                df_historial_total['dt_aux'] = pd.to_datetime(df_historial_total[col_fecha_h], errors='coerce', dayfirst=True)
                pares_aniomes = df_historial_total['dt_aux'].dropna().apply(lambda x: (x.year, x.month)).unique()
                pares_ordenados = sorted(list(pares_aniomes), reverse=True)
                for a, m in pares_ordenados:
                    m_nombre = MESES_ESPANOL.get(m, "")
                    if m_nombre:
                        periodos_disponibles_consulta.append(f"{m_nombre} {a}")

            if "Técnico" in tipo_consulta and col_tec_h and col_prod_h:
                lista_tecnicos = sorted([t for t in df_historial_total[col_tec_h].dropna().astype(str).unique() if t and t.lower() != "nan"])
                tec_elegido = st.selectbox("Seleccionar Técnico:", options=lista_tecnicos, index=None, placeholder="Escribí o seleccioná un técnico...", key=f"{PREFIX_KEYS}_sel_tec")
                
                if tec_elegido:
                    df_tec_filtrado = df_historial_total[df_historial_total[col_tec_h].astype(str).str.lower() == tec_elegido.lower()].copy()
                    
                    periodo_elegido_consulta = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_disponibles_consulta, key=f"{PREFIX_KEYS}_sel_per_tec")
                    
                    if periodo_elegido_consulta != "[ Todos los períodos (Histórico completo) ]":
                        partes = periodo_elegido_consulta.split()
                        mes_str, anio_str = partes[0], int(partes[1])
                        mes_num_sel = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str.lower()][0]
                        df_tec_filtrado = df_tec_filtrado[(df_tec_filtrado['dt_aux'].dt.year == anio_str) & (df_tec_filtrado['dt_aux'].dt.month == mes_num_sel)]

                    lista_prods_tec = sorted([p for p in df_tec_filtrado[col_prod_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                    prod_especifico = st.selectbox("📦 Filtrar por un producto específico (Opcional):", options=["[ Todos los productos ]"] + lista_prods_tec, index=0, key=f"{PREFIX_KEYS}_sel_prod_tec")

                    if prod_especifico != "[ Todos los productos ]":
                        df_tec_filtrado = df_tec_filtrado[df_tec_filtrado[col_prod_h].astype(str).str.lower() == prod_especifico.lower()]

                    total_uni_tec = int(df_tec_filtrado[col_cant_h].apply(convertir_a_numero_precio).sum()) if col_cant_h else len(df_tec_filtrado)
                    
                    if col_fecha_h and 'dt_aux' in df_tec_filtrado.columns:
                        df_tec_filtrado[col_fecha_h] = df_tec_filtrado['dt_aux'].dt.strftime('%d-%m-%Y')

                    st.success(f"👷 **{tec_elegido}** retiró un total de **{total_uni_tec} unidades** según los filtros aplicados.")
                    st.dataframe(df_tec_filtrado.drop(columns=['dt_aux'], errors='ignore'), use_container_width=True, hide_index=True)
                else:
                    st.info("👆 Seleccioná un técnico para ver su historial completo y aplicar filtros.")

            elif "Producto" in tipo_consulta and col_prod_h:
                lista_productos_h = sorted([p for p in df_historial_total[col_prod_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                prod_elegido = st.selectbox("Seleccionar Producto / Insumo:", options=lista_productos_h, index=None, placeholder="Escribí o seleccioná un producto...", key=f"{PREFIX_KEYS}_sel_prod_sal_hist")
                
                if prod_elegido:
                    df_prod_filtrado = df_historial_total[df_historial_total[col_prod_h].astype(str).str.lower() == prod_elegido.lower()].copy()
                    
                    periodo_elegido_consulta_p = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_disponibles_consulta, key=f"{PREFIX_KEYS}_sel_per_prod_sal")
                    
                    if periodo_elegido_consulta_p != "[ Todos los períodos (Histórico completo) ]":
                        partes_p = periodo_elegido_consulta_p.split()
                        mes_str_p, anio_str_p = partes_p[0], int(partes_p[1])
                        mes_num_sel_p = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str_p.lower()][0]
                        df_prod_filtrado = df_prod_filtrado[(df_prod_filtrado['dt_aux'].dt.year == anio_str_p) & (df_prod_filtrado['dt_aux'].dt.month == mes_num_sel_p)]

                    total_uni_prod = int(df_prod_filtrado[col_cant_h].apply(convertir_a_numero_precio).sum()) if col_cant_h else len(df_prod_filtrado)
                    
                    if col_fecha_h and 'dt_aux' in df_prod_filtrado.columns:
                        df_prod_filtrado[col_fecha_h] = df_prod_filtrado['dt_aux'].dt.strftime('%d-%m-%Y')

                    st.success(f"📦 Del producto **{prod_elegido}** se retiraron **{total_uni_prod} unidades** en el período seleccionado.")
                    st.dataframe(df_prod_filtrado.drop(columns=['dt_aux'], errors='ignore'), use_container_width=True, hide_index=True)
                else:
                    st.info("👆 Seleccioná un producto para ver el detalle histórico de sus salidas.")
