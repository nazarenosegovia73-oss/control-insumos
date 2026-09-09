import streamlit as st 
import pandas as pd
import re
import datetime
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Control de Insumos", page_icon="🎨", layout="wide")

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
        
        # Usamos get_all_values() para traer toda la matriz sin cortes ni filtros de cabecera predeterminados
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

# --- CARGA DE DATOS ---
df_inventario_raw = cargar_datos("Inventario Insumos")
df_salida_raw = cargar_datos("salida")
df_ingreso_raw = cargar_datos("ingresos")

# --- BARRA LATERAL ---
if st.sidebar.button("🔄 Refrescar Datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("🔍 Consulta Rápida de Stock")

if df_inventario_raw is not None and not df_inventario_raw.empty:
    df_inv_sidebar = limpiar_tabla(df_inventario_raw)
    col_prod_inv = df_inv_sidebar.columns[1] if len(df_inv_sidebar.columns) > 1 else df_inv_sidebar.columns[0]
    col_stock_inv = next((c for c in df_inv_sidebar.columns if 'stock' in str(c).lower() or 'cantidad' in str(c).lower()), None)
    
    lista_productos = sorted([p for p in df_inv_sidebar[col_prod_inv].unique().tolist() if str(p).strip()])
    prod_seleccionado = st.sidebar.selectbox(
        "Buscar o seleccionar producto:", 
        options=lista_productos, 
        index=None, 
        placeholder="Escribí para buscar..."
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
                        historial_prod = historial_prod.dropna(subset=[col_fecha_ing]).sort_values(by=col_fecha_ing, ascending=True)
                        if not historial_prod.empty:
                            ultima_fecha = historial_prod.iloc[-1][col_fecha_ing]
                            if pd.notna(ultima_fecha):
                                fecha_texto = pd.to_datetime(ultima_fecha).strftime('%d-%m-%Y')

                    if col_prov_ing and col_precio_ing:
                        for prov, grp in historial_prod.groupby(col_prov_ing):
                            prov_nom = str(prov).strip().title()
                            if prov_nom and prov_nom != "0" and prov_nom.lower() != "nan":
                                ult_p = grp.iloc[-1][col_precio_ing]
                                p_fmt = formatear_precio(ult_p) if (pd.notna(ult_p) and ult_p > 0) else "S/D"
                                proveedores_list.append(f"{prov_nom} ({p_fmt})")

        prov_str = "\n  • ".join(proveedores_list) if proveedores_list else "Sin registros"

        st.sidebar.success(
            f"📦 **{prod_seleccionado}**\n\n"
            f"• **Stock Disponible:** {cant_texto}\n"
            f"• **Última Compra:** {fecha_texto}\n"
            f"• **Proveedor(es) y Precio:**\n  • {prov_str}"
        )

# --- PESTAÑAS PRINCIPALES ---
st.title("🎨🛠️ Control de Insumos")

tab_ingreso, tab_salida, tab_reposicion, tab_inventario, tab_indicadores = st.tabs(
    ["📥 Ingresos", "📤 Salida", "🛒 Reposición", "📦 Inventario", "📊 Indicadores"]
)

if "lista_ingresos_pendientes" not in st.session_state:
    st.session_state.lista_ingresos_pendientes = []
if "lista_salidas_pendientes" not in st.session_state:
    st.session_state.lista_salidas_pendientes = []
if "lista_inventario_pendientes" not in st.session_state:
    st.session_state.lista_inventario_pendientes = []

# --- PESTAÑA INGRESOS ---
with tab_ingreso:
    st.subheader("📝 Carga Rápida de Insumos (Ingresos)")
    opciones_prods_col_c = sorted([p for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist() if p and p != "0" and p.lower() != "nan"]) if (df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3) else []
    opciones_proveedores = []
    if df_ingreso_raw is not None and not df_ingreso_raw.empty:
        col_prov_ing = next((c for c in df_ingreso_raw.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'donde', 'comprado', 'local', 'vendedor'])), None)
        if col_prov_ing:
            provs_set = set()
            for p in df_ingreso_raw[col_prov_ing].dropna().astype(str).str.strip().unique().tolist():
                p_str = p.strip().title()
                if p_str and p_str != "0" and p_str.lower() != "nan":
                    provs_set.add(p_str)
            opciones_proveedores = sorted(list(provs_set))

    with st.form("form_agregar_item_ingreso", clear_on_submit=True):
        col_prod, col_fecha = st.columns([3, 1])
        producto_ingresado = col_prod.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Escribí una letra para filtrar...")
        fecha_ingreso = col_fecha.date_input("📅 Fecha de Compra *", value=datetime.date.today())
        
        col_cant, col_precio, col_prov = st.columns([1, 1, 2])
        cantidad_ingresada = col_cant.number_input("🔢 Cantidad *", min_value=1, value=1, step=1)
        precio_ingresado = col_precio.number_input("💵 Precio Unitario ($) *", min_value=0.0, value=0.0, step=100.0)
        
        prov_seleccionado = col_prov.selectbox("🏢 Proveedor *", options=opciones_proveedores, index=None, placeholder="Seleccioná un proveedor...")
        nuevo_prov_escrito = st.text_input("➕ O escribí un nuevo proveedor aquí:", placeholder="Ej: Wurth Argentina").strip()
        proveedor_final = nuevo_prov_escrito.title() if nuevo_prov_escrito else (prov_seleccionado.title() if prov_seleccionado else "")

        observaciones_ingreso = st.text_input("📝 Observaciones:", placeholder="Ej: Factura A N° 000123 / Remito").strip()

        btn_agregar = st.form_submit_button("➕ Agregar a la Lista de Carga", type="secondary", use_container_width=True)

        if btn_agregar:
            errores = []
            if not producto_ingresado: errores.append("Producto / Detalle")
            if cantidad_ingresada <= 0: errores.append("Cantidad")
            if precio_ingresado <= 0: errores.append("Precio Unitario")
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

                st.session_state.lista_ingresos_pendientes.append({
                    "Articulo": articulo_val,
                    "Categoria": categoria_val,
                    "Producto": producto_ingresado,
                    "Marca": marca_val,
                    "Medida": medida_val,
                    "Cantidad": cantidad_ingresada,
                    "Fecha": fecha_ingreso.strftime("%d-%m-%Y"),
                    "Precio Unitario": precio_ingresado,
                    "Precio Total": cantidad_ingresada * precio_ingresado,
                    "Proveedor": proveedor_final,
                    "Observaciones": observaciones_ingreso
                })
                st.toast(f"➕ Agregado a la lista: {producto_ingresado}")
                st.rerun()

    if st.session_state.lista_ingresos_pendientes:
        st.markdown("---")
        st.subheader("🛒 Insumos Pendientes de Guardar (Ingresos)")
        df_pendientes = pd.DataFrame(st.session_state.lista_ingresos_pendientes)
        df_editado = st.data_editor(df_pendientes, num_rows="dynamic", use_container_width=True)
        col_guardar, col_limpiar = st.columns([3, 1])
        if col_guardar.button("💾 Guardar INGRESOS en Google Sheets", type="primary", use_container_width=True):
            client = obtener_cliente_gspread()
            if client:
                try:
                    sheet_ingresos = client.open_by_key(ID_SHEET).worksheet("ingresos")
                    col_c_valores = sheet_ingresos.col_values(3)
                    primera_fila_vacia = len(col_c_valores) + 1
                    filas_a_subir = df_editado.values.tolist()
                    rango_insertar = f"A{primera_fila_vacia}:K{primera_fila_vacia + len(filas_a_subir) - 1}"
                    sheet_ingresos.update(rango_insertar, filas_a_subir)
                    st.success(f"✅ ¡Se guardaron {len(filas_a_subir)} registros en Google Sheets!")
                    st.session_state.lista_ingresos_pendientes = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ Error al escribir en Google Sheets: {err}")
        if col_limpiar.button("🗑️ Cancelar Lista", use_container_width=True):
            st.session_state.lista_ingresos_pendientes = []
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Historial Completo de Ingresos Registrados")
    if df_ingreso_raw is not None and not df_ingreso_raw.empty:
        df_ingreso_tabla = limpiar_tabla(df_ingreso_raw)
        if 'fecha' in df_ingreso_tabla.columns:
            df_ingreso_tabla['fecha'] = pd.to_datetime(df_ingreso_tabla['fecha'], errors='coerce').dt.strftime('%d-%m-%Y')
        st.dataframe(df_ingreso_tabla, use_container_width=True, hide_index=True)

# --- PESTAÑA SALIDA ---
with tab_salida:
    st.subheader("📝 Carga Rápida de Salida de Insumos")
    opciones_prods_col_c = sorted([p for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist() if p and p != "0" and p.lower() != "nan"]) if (df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3) else []
    opciones_tecnicos = []
    if df_salida_raw is not None and not df_salida_raw.empty and len(df_salida_raw.columns) >= 8:
        col_nombre_tec = df_salida_raw.columns[7]
        tecs_set = set()
        for t in df_salida_raw[col_nombre_tec].dropna().astype(str).str.strip().unique().tolist():
            t_str = t.strip().title()
            if t_str and t_str != "0" and t_str.lower() != "nan":
                tecs_set.add(t_str)
        opciones_tecnicos = sorted(list(tecs_set))

    with st.form("form_agregar_item_salida", clear_on_submit=True):
        col_prod_s, col_fecha_s_form = st.columns([3, 1])
        producto_salida = col_prod_s.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Escribí una letra para filtrar...")
        fecha_salida = col_fecha_s_form.date_input("📅 Fecha de Salida *", value=datetime.date.today())
        
        col_cant_s, col_tec_s_form = st.columns([1, 2])
        cantidad_salida = col_cant_s.number_input("🔢 Cantidad *", min_value=1, value=1, step=1)
        tec_seleccionado = col_tec_s_form.selectbox("👷 Nombre / Técnico habitual *", options=opciones_tecnicos, index=None, placeholder="Seleccioná técnico...")
        nuevo_tec_escrito = st.text_input("➕ O escribí un nuevo técnico / responsable:", placeholder="Ej: Roberto Gomez").strip()
        tecnico_final = nuevo_tec_escrito.title() if nuevo_tec_escrito else (tec_seleccionado.title() if tec_seleccionado else "")

        observaciones_salida = st.text_input("📝 Observaciones (Columna L):", placeholder="Ej: Orden N° 1024 / Trabajo de pintura").strip()

        btn_agregar_salida = st.form_submit_button("➕ Agregar Salida a la Lista", type="secondary", use_container_width=True)

        if btn_agregar_salida:
            errores_salida = []
            if not producto_salida: errores_salida.append("Producto / Detalle")
            if cantidad_salida <= 0: errores_salida.append("Cantidad")
            if not tecnico_final: errores_salida.append("Nombre / Técnico")

            if errores_salida:
                st.error(f"⚠️ **Faltan campos:** {', '.join(errores_salida)}")
            else:
                articulo_val, categoria_val, marca_val, medida_val = "", "", "", ""
                if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 5:
                    fila_match = df_inventario_raw[df_inventario_raw.iloc[:, 2].astype(str).str.strip() == str(producto_salida).strip()]
                    if not fila_match.empty:
                        articulo_val = str(fila_match.iloc[0, 0]) if not pd.isna(fila_match.iloc[0, 0]) else ""
                        categoria_val = str(fila_match.iloc[0, 1]) if not pd.isna(fila_match.iloc[0, 1]) else ""
                        marca_val = str(fila_match.iloc[0, 3]) if not pd.isna(fila_match.iloc[0, 3]) else ""
                        medida_val = str(fila_match.iloc[0, 4]) if not pd.isna(fila_match.iloc[0, 4]) else ""

                precio_automatico, proveedor_automatico = 0.0, ""
                if df_ingreso_raw is not None and not df_ingreso_raw.empty:
                    df_ing_limpio_sb = limpiar_tabla(df_ingreso_raw)
                    col_prod_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle', 'descripcion'])), None)
                    col_precio_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
                    col_prov_ing = next((c for c in df_ing_limpio_sb.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'local', 'vendedor'])), None)

                    if col_prod_ing and col_precio_ing:
                        historial_prod = df_ing_limpio_sb[df_ing_limpio_sb[col_prod_ing].astype(str).str.lower() == str(producto_salida).lower()]
                        if not historial_prod.empty:
                            precios_historicos = historial_prod[col_precio_ing].dropna().apply(convertir_a_numero_precio)
                            if not precios_historicos.empty:
                                precio_automatico = float(precios_historicos.max())
                            
                            if col_prov_ing:
                                ultimo_registro = historial_prod.iloc[-1]
                                if pd.notna(ultimo_registro[col_prov_ing]):
                                    proveedor_automatico = str(ultimo_registro[col_prov_ing]).strip().title()

                precio_total_calc = precio_automatico * cantidad_salida

                st.session_state.lista_salidas_pendientes.append({
                    "articulo": articulo_val, 
                    "Categoría": categoria_val, 
                    "Producto / Detalle": producto_salida,
                    "Marca": marca_val, 
                    "Medida / Variedad": medida_val, 
                    "cantidad": cantidad_salida,
                    "fecha": fecha_salida.strftime("%d-%m-%Y"), 
                    "nombre": tecnico_final,
                    "precio": precio_automatico, 
                    "precio_total": precio_total_calc,
                    "proveedor": proveedor_automatico,
                    "observaciones": observaciones_salida
                })
                st.toast(f"➕ Agregado a salidas: {producto_salida}")
                st.rerun()

    if st.session_state.lista_salidas_pendientes:
        st.markdown("---")
        st.subheader("🛒 Salidas Pendientes de Guardar")
        df_pendientes_s = pd.DataFrame(st.session_state.lista_salidas_pendientes)
        df_editado_s = st.data_editor(df_pendientes_s, num_rows="dynamic", use_container_width=True)
        col_guardar_s, col_limpiar_s = st.columns([3, 1])
        if col_guardar_s.button("💾 Guardar SALIDAS en Google Sheets", type="primary", use_container_width=True):
            client = obtener_cliente_gspread()
            if client:
                try:
                    sheet_salida = client.open_by_key(ID_SHEET).worksheet("salida")
                    col_c_valores = sheet_salida.col_values(3)
                    primera_fila_vacia = len(col_c_valores) + 1
                    filas_a_subir = df_editado_s.values.tolist()
                    rango_insertar = f"A{primera_fila_vacia}:L{primera_fila_vacia + len(filas_a_subir) - 1}"
                    sheet_salida.update(rango_insertar, filas_a_subir)
                    st.success(f"✅ ¡Se guardaron {len(filas_a_subir)} salidas en Google Sheets!")
                    st.session_state.lista_salidas_pendientes = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ Error al escribir en Google Sheets: {err}")
        if col_limpiar_s.button("🗑️ Cancelar Lista (Salidas)", use_container_width=True):
            st.session_state.lista_salidas_pendientes = []
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Historial Completo de Salidas Registradas")
    if df_salida_raw is not None and not df_salida_raw.empty:
        df_salida_tabla = limpiar_tabla(df_salida_raw)
        if 'fecha' in df_salida_tabla.columns:
            df_salida_tabla['fecha'] = pd.to_datetime(df_salida_tabla['fecha'], errors='coerce').dt.strftime('%d-%m-%Y')
        st.dataframe(df_salida_tabla, use_container_width=True, hide_index=True)

# --- PESTAÑA REPOSICIÓN ---
with tab_reposicion:
    st.subheader("🛒 Control y Gestión de Reposición")
    
    if df_inventario_raw is not None and not df_inventario_raw.empty:
        df_rep = limpiar_tabla(df_inventario_raw)
        
        col_f1, col_f2 = st.columns([2, 2])
        filtro_estado = col_f1.radio(
            "Visualizar:", 
            options=["🔴 Solo insumos a reponer", "📋 Ver todo el inventario"], 
            horizontal=True,
            key="radio_filtro_reposicion"
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
                if st.button("📋 Copiar / Ver resumen de faltantes para enviar", type="primary", key="btn_resumen_faltantes"):
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
                    
                    st.text_area("Copiá este texto para pasarlo por WhatsApp o email:", value=resumen_texto, height=220)
        else:
            st.success("🎉 ¡Excelente noticia! No hay ningún insumo que requiera reposición en este momento.")

# --- PESTAÑA INVENTARIO ---
with tab_inventario:
    st.subheader("➕ Agregar Nuevo Artículo al Inventario")
    
    with st.form("form_nuevo_inventario", clear_on_submit=True):
        col_cat, col_prod_inv = st.columns([1, 2])
        categoria_input = col_cat.text_input("📂 Categoría *", placeholder="Ej: Pinturas, Lijas, Enmascarado").strip().title()
        producto_input = col_prod_inv.text_input("📦 Producto / Detalle Nuevo *", placeholder="Ej: Lija al agua 220").strip()

        col_marca, col_ubic = st.columns([2, 2])
        marca_input = col_marca.text_input("🏷️ Marca", placeholder="Ej: PPG, Norton, Wurth").strip()
        ubicacion_input = col_ubic.text_input("📍 Ubicación", placeholder="Ej: Depósito 1, Estante A").strip()

        col_medida, col_stock_ini, col_min_inv = st.columns([2, 1, 1])
        opciones_medidas = ["bolsas", "cajas", "litros", "unidad"]
        medida_input = col_medida.selectbox("📏 Medida / Unidad *", options=opciones_medidas, index=None, placeholder="Seleccionar medida...")
        stock_input = col_stock_ini.number_input("📦 Stock Inicial", min_value=0, step=1, value=0)
        min_input = col_min_inv.number_input("⚠️ Stock Mínimo", min_value=0, step=1, value=2)

        btn_agregar_inv = st.form_submit_button("➕ Agregar Artículo a la Lista de Inventario", type="secondary", use_container_width=True)

        if btn_agregar_inv:
            errores_inv = []
            if not categoria_input: errores_inv.append("Categoría")
            if not producto_input: errores_inv.append("Producto / Detalle")
            if not medida_input: errores_inv.append("Medida / Unidad")

            opciones_prods_existentes = []
            if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3:
                for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist():
                    if p and p != "0" and p.lower() != "nan":
                        opciones_prods_existentes.append(p.lower())
            for pend in st.session_state.lista_inventario_pendientes:
                if "producto" in pend and pend["producto"]:
                    opciones_prods_existentes.append(str(pend["producto"]).strip().lower())

            if producto_input and producto_input.lower() in set(opciones_prods_existentes):
                errores_inv.append(f"El producto '{producto_input}' ya existe en el inventario. Ingrese uno diferente.")

            if errores_inv:
                st.error(f"⚠️ **Atención:** {', '.join(errores_inv)}")
            else:
                todos_los_codigos = []
                if df_inventario_raw is not None and not df_inventario_raw.empty:
                    col_cods = df_inventario_raw.iloc[:, 0].dropna().astype(str).tolist()
                    todos_los_codigos.extend([c.strip() for c in col_cods if c.strip() and c.strip() != "0" and c.strip().lower() != "nan"])
                for pend in st.session_state.lista_inventario_pendientes:
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

                st.session_state.lista_inventario_pendientes.append({
                    "articulo": nuevo_codigo,
                    "categoria": categoria_input,
                    "producto": producto_input,
                    "marca": marca_input,
                    "medida": medida_input,
                    "real": stock_input,
                    "stock_actual": stock_input,
                    "stock_minimo": min_input,
                    "ubicacion": ubicacion_input
                })

                st.toast(f"➕ Agregado al inventario pendiente: {producto_input}")
                st.rerun()

    if st.session_state.lista_inventario_pendientes:
        st.markdown("---")
        st.subheader("🛒 Inventarios Pendientes de Guardar")
        df_pendientes_inv = pd.DataFrame(st.session_state.lista_inventario_pendientes)
        df_editado_inv = st.data_editor(df_pendientes_inv, num_rows="dynamic", use_container_width=True)
        col_guardar_inv, col_limpiar_inv = st.columns([3, 1])
        
        if col_guardar_inv.button("💾 Guardar INVENTARIO en Google Sheets", type="primary", use_container_width=True):
            client = obtener_cliente_gspread()
            if client:
                try:
                    sheet_inv = client.open_by_key(ID_SHEET).worksheet("Inventario Insumos")
                    col_a_valores = sheet_inv.col_values(1)
                    primera_fila_vacia = len(col_a_valores) + 1
                    cant_filas = len(df_editado_inv)

                    bloque_A_G = df_editado_inv[["articulo", "categoria", "producto", "marca", "medida", "real", "stock_actual"]].values.tolist()
                    bloque_I = [[row["stock_minimo"]] for _, row in df_editado_inv.iterrows()]
                    bloque_K = [[row["ubicacion"]] for _, row in df_editado_inv.iterrows()]

                    sheet_inv.update(f"A{primera_fila_vacia}:G{primera_fila_vacia + cant_filas - 1}", bloque_A_G)
                    sheet_inv.update(f"I{primera_fila_vacia}:I{primera_fila_vacia + cant_filas - 1}", bloque_I)
                    sheet_inv.update(f"K{primera_fila_vacia}:K{primera_fila_vacia + cant_filas - 1}", bloque_K)

                    st.success(f"✅ ¡Se guardaron {cant_filas} artículos en Google Sheets!")
                    st.session_state.lista_inventario_pendientes = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ Error al escribir en Google Sheets: {err}")
                    
        if col_limpiar_inv.button("🗑️ Cancelar Lista (Inventario)", use_container_width=True):
            st.session_state.lista_inventario_pendientes = []
            st.rerun()

    st.markdown("---")
    st.subheader("📦 Tabla Completa de Inventario")
    if df_inventario_raw is not None and not df_inventario_raw.empty:
        df_inv_tabla = limpiar_tabla(df_inventario_raw, mantener_dif=True)
        st.dataframe(df_inv_tabla, use_container_width=True, hide_index=True)

# --- PESTAÑA INDICADORES ---
with tab_indicadores:
    st.subheader("📊 Panel de Control y Costos por Paño")

    df_salida_limp = limpiar_tabla(df_salida_raw) if df_salida_raw is not None and not df_salida_raw.empty else pd.DataFrame()
    
    anio_sheet = 2026
    dict_panos_sheet = {}
    
    client_ind = obtener_cliente_gspread()
    if client_ind:
        try:
            sheet_ind_obj = client_ind.open_by_key(ID_SHEET).worksheet("indicadores")
            filas_ind = sheet_ind_obj.get_all_values()
            if filas_ind and len(filas_ind) > 0:
                try:
                    anio_sheet = int(str(filas_ind[0][0]).strip())
                except:
                    anio_sheet = 2026
                
                mes_map_dict = {
                    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
                    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
                    "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                }
                for f in filas_ind[1:]:
                    if len(f) >= 2:
                        m_txt = str(f[0]).strip().lower()
                        p_txt = str(f[1]).strip()
                        if m_txt and m_txt != "total":
                            for m_nom, m_num in mes_map_dict.items():
                                if m_nom in m_txt:
                                    try:
                                        val_p = int(float(p_txt.replace(",", "."))) if p_txt else 0
                                        if val_p > 0:
                                            dict_panos_sheet[(anio_sheet, m_num)] = val_p
                                    except:
                                        pass
        except Exception as e:
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
    for (anio_val, mes_num) in sorted(list(meses_a_procesar), key=lambda x: (x[0], x[1]), reverse=True):
        nombre_m = lista_meses_nombres[int(mes_num) - 1]
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

    df_resumen = pd.DataFrame(resumen_meses)

    periodos_disponibles_set = {(item["orden_cronologico"] // 100, item["orden_cronologico"] % 100, item["Período / Mes"]) for item in resumen_meses}
    periodos_ordenados = sorted(list(periodos_disponibles_set), key=lambda x: (x[0], x[1]), reverse=True)
    lista_opciones_str = [p[2] for p in periodos_ordenados]

    opciones_periodo = ["Todos (Histórico con Datos)"] + lista_opciones_str
    periodo_seleccionado = st.selectbox("📅 Período de Análisis (para KPIs de Costos y Paños):", options=opciones_periodo, index=0, key="sel_periodo_kpi_final")

    st.markdown("---")

    if "Todos" in periodo_seleccionado:
        total_consumo = df_resumen["Consumo Insumos ($)"].sum() if not df_resumen.empty else 0.0
        total_panos = df_resumen["Paños Realizados"].sum() if not df_resumen.empty else 0
        costo_promedio = (total_consumo / total_panos) if total_panos > 0 else 0.0
    else:
        fila_sel = df_resumen[df_resumen["Período / Mes"] == periodo_seleccionado] if not df_resumen.empty else pd.DataFrame()
        if not fila_sel.empty:
            total_consumo = fila_sel.iloc[0]["Consumo Insumos ($)"]
            total_panos = int(fila_sel.iloc[0]["Paños Realizados"])
            costo_promedio = (total_consumo / total_panos) if total_panos > 0 else 0.0
        else:
            total_consumo = 0.0
            total_panos = 0
            costo_promedio = 0.0

    st.markdown("### 📈 Indicadores Globales de Producción y Costos")
    
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric(label="CONSUMO DE INS. (REGISTRADO)", value=formatear_precio(total_consumo))
    kpi2.metric(label="PAÑOS REALIZADOS", value=f"{total_panos}")
    kpi3.metric(label="COSTO PROMEDIO X PAÑO", value=formatear_precio(costo_promedio))

    if not df_resumen.empty:
        st.markdown("---")
        st.markdown("### 📊 Evolución Mensual de Consumo de Insumos")
        df_grafico = df_resumen.sort_values(by="orden_cronologico", ascending=True).set_index("Período / Mes")[["Consumo Insumos ($)"]]
        
        tipo_grafico = st.radio("Tipo de visualización:", options=["Gráfico de Líneas 📈", "Gráfico de Barras 📊"], horizontal=True, key="tipo_grafico_evolucion")
        if "Líneas" in tipo_grafico:
            st.line_chart(df_grafico)
        else:
            st.bar_chart(df_grafico)

    st.markdown("---")

    st.markdown("### 📋 Resumen Histórico (Meses con Movimiento)")
    if not df_resumen.empty:
        df_resumen_display = df_resumen.sort_values(by="orden_cronologico", ascending=False).head(6).drop(columns=["orden_cronologico"]).copy()
        df_resumen_display["Consumo Insumos ($)"] = df_resumen_display["Consumo Insumos ($)"].apply(formatear_precio)
        df_resumen_display["Costo por Paño ($)"] = df_resumen_display["Costo por Paño ($)"].apply(formatear_precio)
        st.dataframe(df_resumen_display, use_container_width=True, hide_index=True)
    else:
        st.info("Todavía no hay registros con consumos o paños cargados para mostrar en el histórico.")

    st.markdown("---")
    st.subheader("🏆 Análisis y Rankings del Taller")

    opciones_ranking = ["Histórico Completo (Acumulado)"] + lista_opciones_str
    periodo_ranking_sel = st.selectbox("📅 Filtrar Rankings por Período:", options=opciones_ranking, index=0, key="sel_periodo_ranking_taller")

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
        key="radio_consulta_ing_ind"
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
            prov_elegido = st.selectbox("Seleccionar Proveedor:", options=lista_proveedores, index=None, placeholder="Escribí o seleccioná un proveedor...", key="sel_prov_filtro_ind")
            
            if prov_elegido:
                df_prov_filtrado = df_ing_historial[df_ing_historial[col_prov_h].astype(str).str.lower() == prov_elegido.lower()].copy()
                
                periodo_elegido_ing = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_ing_disp, key="sel_periodo_prov_ind")
                
                if periodo_elegido_ing != "[ Todos los períodos (Histórico completo) ]":
                    partes = periodo_elegido_ing.split()
                    mes_str, anio_str = partes[0], int(partes[1])
                    mes_num_sel = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str.lower()][0]
                    df_prov_filtrado = df_prov_filtrado[(df_prov_filtrado['dt_aux_ing'].dt.year == anio_str) & (df_prov_filtrado['dt_aux_ing'].dt.month == mes_num_sel)]

                lista_prods_prov = sorted([p for p in df_prov_filtrado[col_prod_ing_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                prod_esp_prov = st.selectbox("📦 Filtrar por un producto específico (Opcional):", options=["[ Todos los productos ]"] + lista_prods_prov, index=0, key="sel_prod_prov_ind")

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
            prod_ing_elegido = st.selectbox("Seleccionar Producto / Insumo (Ingresos):", options=lista_productos_ing, index=None, placeholder="Escribí o seleccioná un producto...", key="sel_prod_ing_filtro_ind")
            
            if prod_ing_elegido:
                df_prod_ing_filtrado = df_ing_historial[df_ing_historial[col_prod_ing_h].astype(str).str.lower() == prod_ing_elegido.lower()].copy()
                
                periodo_elegido_ing_p = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_ing_disp, key="sel_periodo_prod_ing_ind")
                
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
        key="radio_consulta_sal_ind"
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
            tec_elegido = st.selectbox("Seleccionar Técnico:", options=lista_tecnicos, index=None, placeholder="Escribí o seleccioná un técnico...", key="sel_tec_filtro_ind")
            
            if tec_elegido:
                df_tec_filtrado = df_historial_total[df_historial_total[col_tec_h].astype(str).str.lower() == tec_elegido.lower()].copy()
                
                periodo_elegido_consulta = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_disponibles_consulta, key="sel_periodo_tec_ind")
                
                if periodo_elegido_consulta != "[ Todos los períodos (Histórico completo) ]":
                    partes = periodo_elegido_consulta.split()
                    mes_str, anio_str = partes[0], int(partes[1])
                    mes_num_sel = [k for k, v in MESES_ESPANOL.items() if v.lower() == mes_str.lower()][0]
                    df_tec_filtrado = df_tec_filtrado[(df_tec_filtrado['dt_aux'].dt.year == anio_str) & (df_tec_filtrado['dt_aux'].dt.month == mes_num_sel)]

                lista_prods_tec = sorted([p for p in df_tec_filtrado[col_prod_h].dropna().astype(str).unique() if p and p.lower() != "nan"])
                prod_especifico = st.selectbox("📦 Filtrar por un producto específico (Opcional):", options=["[ Todos los productos ]"] + lista_prods_tec, index=0, key="sel_prod_tec_ind")

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
            prod_elegido = st.selectbox("Seleccionar Producto / Insumo:", options=lista_productos_h, index=None, placeholder="Escribí o seleccioná un producto...", key="sel_prod_filtro_ind")
            
            if prod_elegido:
                df_prod_filtrado = df_historial_total[df_historial_total[col_prod_h].astype(str).str.lower() == prod_elegido.lower()].copy()
                
                periodo_elegido_consulta_p = st.selectbox("📅 Filtrar por Período (Opcional):", options=periodos_disponibles_consulta, key="sel_periodo_prod_ind_s")
                
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
                st.info("👆 Seleccioná un producto para ver el detalle histórico y filtrar por período si lo deseás.")

    st.markdown("---")
    st.subheader("🏷️ Indicadores de Stock e Insumos")
    
    df_inv_limpio_ind = limpiar_tabla(df_inventario_raw) if df_inventario_raw is not None and not df_inventario_raw.empty else pd.DataFrame()
    total_articulos = len(df_inv_limpio_ind)
    porcentaje_critico = 0.0
    
    cols_lower_ind = {str(c).lower().strip(): c for c in df_inv_limpio_ind.columns}
    col_est_ind = next((cols_lower_ind[c] for c in cols_lower_ind if 'estado' in c), None)
    
    if col_est_ind and total_articulos > 0:
        cant_reponer = len(df_inv_limpio_ind[df_inv_limpio_ind[col_est_ind].astype(str).str.strip().str.upper() == "REPONER"])
        porcentaje_critico = (cant_reponer / total_articulos) * 100

    valor_inmovilizado = 0.0
    if not df_inv_limpio_ind.empty:
        col_stock_act = next((cols_lower_ind[c] for c in cols_lower_ind if ('stock' in c or 'actual' in c) and 'min' not in c), None)
        col_prod_inv_ind = next((cols_lower_ind[c] for c in cols_lower_ind if any(k in c for k in ['producto', 'detalle', 'insumo'])), None)
        
        mapa_precios = {}
        if df_ingreso_raw is not None and not df_ingreso_raw.empty:
            df_ing_aux = limpiar_tabla(df_ingreso_raw)
            c_p_ing = next((c for c in df_ing_aux.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle'])), None)
            c_pr_ing = next((c for c in df_ing_aux.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
            if c_p_ing and c_pr_ing:
                for _, r_ing in df_ing_aux.iterrows():
                    p_nom = str(r_ing[c_p_ing]).strip().lower()
                    p_val = convertir_a_numero_precio(r_ing[c_pr_ing])
                    if p_val > 0:
                        mapa_precios[p_nom] = p_val
        
        if col_stock_act and col_prod_inv_ind:
            for _, r in df_inv_limpio_ind.iterrows():
                p_n = str(r[col_prod_inv_ind]).strip().lower()
                s_cant = float(r[col_stock_act]) if pd.notna(r[col_stock_act]) else 0.0
                precio_unit = mapa_precios.get(p_n, 0.0)
                valor_inmovilizado += s_cant * precio_unit

    ind_kpi1, ind_kpi2 = st.columns(2)
    ind_kpi1.metric(label="⚠️ % DE INSUMOS EN ESTADO CRÍTICO", value=f"{porcentaje_critico:.1f}%")
    ind_kpi2.metric(label="💰 VALOR TOTAL INMOVILIZADO EN STOCK", value=formatear_precio(valor_inmovilizado))
