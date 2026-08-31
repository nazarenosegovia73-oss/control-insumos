import streamlit as st
import pandas as pd
import re
import datetime
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Control de Insumos", page_icon="🎨", layout="wide")

ID_SHEET = "1cJ6FH-lJWn52UzhMRAEhpIZ-FRcdfJNzwYtouAQE0CE"
RUTA_CREDANCIALES = "credenciales.json"

MESES_ESPANOL = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}

def obtener_cliente_gspread():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        if os.path.exists(RUTA_CREDANCIALES):
            creds = ServiceAccountCredentials.from_json_keyfile_name(RUTA_CREDANCIALES, scope)
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
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        st.error(f"No se pudo cargar la hoja '{nombre_hoja}': {e}")
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
        s = s.replace(',', '') if s.find(',') < s.find('.') else s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.') if len(s.split(',')[-1]) == 2 else s.replace(',', '')
    elif '.' in s and len(s.split('.')[-1]) == 3:
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
            serie_fechas = df_limpio[col].astype(str).str.strip().str.replace('-', '/')
            df_limpio[col] = pd.to_datetime(serie_fechas, errors='coerce', dayfirst=True)
            df_limpio.loc[df_limpio[col].dt.year < 2020, col] = pd.NaT
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

df_inventario_raw = cargar_datos("Inventario Insumos")
df_salida_raw = cargar_datos("salida")
df_ingreso_raw = cargar_datos("ingresos")

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
        
        prov_seleccionado = col_prov.selectbox("🏢 Proveedor habitual *", options=opciones_proveedores, index=None, placeholder="Seleccioná un proveedor...")
        nuevo_prov_escrito = st.text_input("➕ O escribí un nuevo proveedor aquí:", placeholder="Ej: Wurth Argentina").strip()
        proveedor_final = nuevo_prov_escrito.title() if nuevo_prov_escrito else (prov_seleccionado.title() if prov_seleccionado else "")

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
                    "Articulo": articulo_val, "Categoria": categoria_val, "Producto": producto_ingresado,
                    "Marca": marca_val, "Medida": medida_val, "Cantidad": cantidad_ingresada,
                    "Fecha": fecha_ingreso.strftime("%d-%m-%Y"), "Precio Unitario": precio_ingresado,
                    "Precio Total": cantidad_ingresada * precio_ingresado, "Proveedor": proveedor_final
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
                    rango_insertar = f"A{primera_fila_vacia}:J{primera_fila_vacia + len(filas_a_subir) - 1}"
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
        producto_salida = col_prod_s.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Escribí una letra para filtrar...", key="select_prod_salida")
        fecha_salida = col_fecha_s_form.date_input("📅 Fecha de Salida *", value=datetime.date.today(), key="fecha_salida_input")
        
        col_cant_s, col_tec_s_form = st.columns([1, 2])
        cantidad_salida = col_cant_s.number_input("🔢 Cantidad *", min_value=1, value=1, step=1, key="cant_salida_input")
        tec_seleccionado = col_tec_s_form.selectbox("👷 Nombre / Técnico habitual *", options=opciones_tecnicos, index=None, placeholder="Seleccioná técnico...", key="tec_select_input")
        nuevo_tec_escrito = st.text_input("➕ O escribí un nuevo técnico / responsable aquí:", placeholder="Ej: Roberto Gomez").strip()
        tecnico_final = nuevo_tec_escrito.title() if nuevo_tec_escrito else (tec_seleccionado.title() if tec_seleccionado else "")

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

                st.session_state.lista_salidas_pendientes.append({
                    "articulo": articulo_val, "Categoría": categoria_val, "Producto / Detalle": producto_salida,
                    "Marca": marca_val, "Medida / Variedad": medida_val, "cantidad": cantidad_salida,
                    "fecha": fecha_salida.strftime("%d-%m-%Y"), "nombre": tecnico_final,
                    "precio": precio_automatico, "proveedor": proveedor_automatico
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
                    rango_insertar = f"A{primera_fila_vacia}:J{primera_fila_vacia + len(filas_a_subir) - 1}"
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
    st.subheader("📋 Historial de Salidas Registradas")
    if df_salida_raw is not None and not df_salida_raw.empty:
        df_salida_tabla = limpiar_tabla(df_salida_raw)
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
    
    opciones_categorias = []
    if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 2:
        cats_set = set(c.title() for c in df_inventario_raw.iloc[:, 1].dropna().astype(str).str.strip().unique().tolist() if c and c != "0" and c.lower() != "nan")
        opciones_categorias = sorted(list(cats_set))

    col_cat1, col_cat2 = st.columns([2, 1])
    cat_seleccionada = col_cat1.selectbox("📂 Categoría Existente *", options=opciones_categorias, index=None, placeholder="Escribí una letra para filtrar...")
    nueva_cat_escrita = col_cat2.text_input("➕ O nueva categoría:", placeholder="Ej: Pinturas").strip()
    categoria_final = nueva_cat_escrita.title() if nueva_cat_escrita else (cat_seleccionada if cat_seleccionada else "")

    opciones_prods_existentes = []
    if df_inventario_raw is not None and not df_inventario_raw.empty and len(df_inventario_raw.columns) >= 3:
        for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist():
            if p and p != "0" and p.lower() != "nan":
                opciones_prods_existentes.append(p)
    for pend in st.session_state.lista_inventario_pendientes:
        if "producto" in pend and pend["producto"]:
            opciones_prods_existentes.append(str(pend["producto"]).strip())
    opciones_prods_existentes = sorted(list(set(opciones_prods_existentes)))

    col_prod_inv1, col_prod_inv2 = st.columns([2, 1])
    prod_seleccionado_inv = col_prod_inv1.selectbox(
        "📦 Producto Existente *", 
        options=opciones_prods_existentes, 
        index=None, 
        placeholder="Escribí una letra para buscar coincidencias..."
    )
    nuevo_prod_escrito = col_prod_inv2.text_input(
        "➕ O nuevo producto:", 
        placeholder="Ej: Lija 220 (Escribí acá si no hay coincidencia)"
    ).strip()
    
    producto_final = nuevo_prod_escrito if nuevo_prod_escrito else (prod_seleccionado_inv if prod_seleccionado_inv else "")

    marca_nueva = st.text_input("🏷️ Marca", placeholder="Ej: PPG").strip()

    col_medida, col_stock_ini, col_min_inv = st.columns([2, 1, 1])
    opciones_medidas = ["bolsas", "cajas", "litros", "unidad"]
    medida_seleccionada = col_medida.selectbox("📏 Medida / Unidad *", options=opciones_medidas, index=None, placeholder="Seleccionar medida...")
    stock_inicial = col_stock_ini.number_input("📦 Stock Inicial", min_value=0, value=0, step=1)
    stock_minimo = col_min_inv.number_input("⚠️ Stock Mínimo", min_value=0, value=2, step=1)

    if st.button("➕ Agregar Artículo a la Lista de Inventario", type="secondary", use_container_width=True):
        errores_inv = []
        if not categoria_final: errores_inv.append("Categoría")
        if not producto_final: errores_inv.append("Producto / Detalle")
        if not medida_seleccionada: errores_inv.append("Medida / Unidad")

        productos_existentes_set = set(p.lower() for p in opciones_prods_existentes)
        if producto_final and producto_final.lower() in productos_existentes_set and nuevo_prod_escrito:
            errores_inv.append(f"El producto '{producto_final}' ya existe. Por favor modificalo o seleccionalo de la lista.")

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
                "articulo": nuevo_codigo, "categoria": categoria_final, "producto": producto_final,
                "marca": marca_nueva, "medida": medida_seleccionada,
                "stock_inicial": stock_inicial, "stock_minimo": stock_minimo
            })
            st.toast(f"➕ Artículo agregado: {producto_final}")
            st.rerun()

    if st.session_state.lista_inventario_pendientes:
        st.markdown("---")
        st.subheader("🛒 Nuevos Artículos Pendientes")
        df_pendientes_inv = pd.DataFrame(st.session_state.lista_inventario_pendientes)
        df_editado_inv = st.data_editor(df_pendientes_inv, num_rows="dynamic", use_container_width=True)
        col_guardar_inv, col_limpiar_inv = st.columns([3, 1])
        if col_guardar_inv.button("💾 Guardar NUEVOS ARTÍCULOS en Google Sheets", type="primary", use_container_width=True):
            client = obtener_cliente_gspread()
            if client:
                try:
                    sheet_inventario = client.open_by_key(ID_SHEET).worksheet("Inventario Insumos")
                    primera_fila_vacia = len(sheet_inventario.col_values(1)) + 1
                    filas_a_subir = []
                    for index, row in df_editado_inv.iterrows():
                        f_act = primera_fila_vacia + len(filas_a_subir)
                        filas_a_subir.append([
                            str(row.get("articulo", "")), str(row.get("categoria", "")), str(row.get("producto", "")),
                            str(row.get("marca", "")), str(row.get("medida", "")), int(row.get("stock_inicial", 0)),
                            int(row.get("stock_inicial", 0)), f"=G{f_act}-F{f_act}", int(row.get("stock_minimo", 0)),
                            f'=SI(G{f_act}<=I{f_act}; "REPONER"; "OK")'
                        ])
                    
                    rango = f"A{primera_fila_vacia}:J{primera_fila_vacia + len(filas_a_subir) - 1}"
                    sheet_inventario.update(rango, filas_a_subir, value_input_option='USER_ENTERED')
                    
                    for idx, row in enumerate(df_editado_inv.iterrows()):
                        f_act = primera_fila_vacia + idx
                        st_ini = int(row[1].get("stock_inicial", 0))
                        st_min = int(row[1].get("stock_minimo", 0))
                        
                        color_f = {"red": 0.97, "green": 0.84, "blue": 0.85} if st_ini <= st_min else {"red": 0.94, "green": 0.94, "blue": 0.94}
                        color_t = {"red": 0.44, "green": 0.11, "blue": 0.12} if st_ini <= st_min else {"red": 0.0, "green": 0.0, "blue": 0.0}
                        sheet_inventario.format(f"J{f_act}", {"backgroundColor": color_f, "textFormat": {"foregroundColor": color_t, "bold": True}})
                    
                    st.success(f"✅ ¡Se agregaron {len(filas_a_subir)} artículos nuevos al inventario!")
                    st.session_state.lista_inventario_pendientes = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ Error: {err}")

        if col_limpiar_inv.button("🗑️ Cancelar Lista", use_container_width=True):
            st.session_state.lista_inventario_pendientes = []
            st.rerun()

    st.markdown("---")
    st.subheader("📦 Inventario General de Insumos")
    if df_inventario_raw is not None and not df_inventario_raw.empty:
        st.dataframe(limpiar_tabla(df_inventario_raw), use_container_width=True, hide_index=True)

# --- PESTAÑA INDICADORES Y COSTO POR PAÑO (ESTILO KPI CARDS) ---
with tab_indicadores:
    st.subheader("📊 Panel de Control y KPIs del Taller")
    st.markdown("---")

    df_ing_limpio = pd.DataFrame()
    meses_disponibles = []
    
    if df_ingreso_raw is not None and not df_ingreso_raw.empty:
        df_ing_limpio = limpiar_tabla(df_ingreso_raw)
        col_prod_ing = next((c for c in df_ing_limpio.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle', 'descripcion'])), None)
        col_precio_ing = next((c for c in df_ing_limpio.columns if any(k in str(c).lower() for k in ['precio', 'costo', 'valor'])), None)
        col_fecha_ing = next((c for c in df_ing_limpio.columns if 'fecha' in str(c).lower()), None)

        if col_prod_ing and col_precio_ing:
            df_ing_limpio['producto_lower'] = df_ing_limpio[col_prod_ing].astype(str).str.strip().str.lower()
            df_ing_limpio['precio_num'] = df_ing_limpio[col_precio_ing].apply(convertir_a_numero_precio)
            
            if col_fecha_ing:
                df_ing_limpio['AnioMes'] = df_ing_limpio[col_fecha_ing].dt.to_period('M')
                meses_disponibles = sorted([p for p in df_ing_limpio['AnioMes'].dropna().unique()], reverse=True)

    gasto_por_salidas_total = 0.0
    gastos_salidas_por_mes = {}
    
    if df_salida_raw is not None and not df_salida_raw.empty:
        df_salida_limpio = limpiar_tabla(df_salida_raw)
        col_fecha_sal = next((c for c in df_salida_limpio.columns if 'fecha' in str(c).lower()), None)
        col_prod_sal = next((c for c in df_salida_limpio.columns if any(k in str(c).lower() for k in ['producto', 'detalle', 'insumo'])), None)
        col_cant_sal = next((c for c in df_salida_limpio.columns if any(k in str(c).lower() for k in ['cantidad', 'cant'])), None)

        if col_prod_sal and col_cant_sal:
            if col_fecha_sal:
                df_salida_limpio['AnioMes'] = df_salida_limpio[col_fecha_sal].dt.to_period('M')

            for _, r_sal in df_salida_limpio.iterrows():
                p_nom = str(r_sal[col_prod_sal]).strip().lower()
                cant_retirada = convertir_a_numero_precio(r_sal[col_cant_sal])
                fecha_salida_reg = r_sal[col_fecha_sal] if (col_fecha_sal and pd.notna(r_sal[col_fecha_sal])) else None
                
                precio_u_max = 0.0
                if not df_ing_limpio.empty and 'producto_lower' in df_ing_limpio.columns:
                    mask = (df_ing_limpio['producto_lower'] == p_nom)
                    if fecha_salida_reg and col_fecha_ing:
                        mask = mask & (df_ing_limpio[col_fecha_ing] <= fecha_salida_reg)
                    
                    historial_previo = df_ing_limpio[mask]
                    if not historial_previo.empty:
                        precio_u_max = float(historial_previo['precio_num'].max())
                    else:
                        historial_general = df_ing_limpio[df_ing_limpio['producto_lower'] == p_nom]
                        if not historial_general.empty:
                            precio_u_max = float(historial_general['precio_num'].max())

                subtotal_movimiento = cant_retirada * precio_u_max
                gasto_por_salidas_total += subtotal_movimiento
                
                if col_fecha_sal and pd.notna(r_sal['AnioMes']):
                    per = r_sal['AnioMes']
                    gastos_salidas_por_mes[per] = gastos_salidas_por_mes.get(per, 0.0) + subtotal_movimiento

    if "panios_por_mes" not in st.session_state:
        st.session_state.panios_por_mes = {}

    # Construir opciones de meses disponibles o año actual
    anio_actual = datetime.date.today().year
    opciones_meses = ["📅 Todos (Histórico Completo)"]
    for m_num in range(1, 13):
        opciones_meses.append(f"{MESES_ESPANOL[m_num].capitalize()} {anio_actual}")

    # Selector de período estilo la captura del usuario
    col_sel_p1, col_sel_p2 = st.columns([2, 2])
    periodo_seleccionado = col_sel_p1.selectbox(
        "📅 Período de Análisis:",
        options=opciones_meses,
        index=0,
        key="select_periodo_kpi"
    )

    # Calcular datos según el período elegido
    consumo_insumos_sel = 0.0
    if periodo_seleccionado.startswith("📅 Todos"):
        consumo_insumos_sel = gasto_por_salidas_total
        clave_panio = "Historico_Total"
    else:
        # Extraer mes y año
        partes = periodo_seleccionado.split()
        nombre_mes = partes[0].lower()
        anio_mes = int(partes[1])
        num_mes = next((k for k, v in MESES_ESPANOL.items() if v == nombre_mes), 1)
        
        per_obj = pd.Period(year=anio_mes, month=num_mes, freq='M')
        consumo_insumos_sel = gastos_salidas_por_mes.get(per_obj, 0.0)
        clave_panio = periodo_seleccionado

    panios_actuales = st.session_state.panios_por_mes.get(clave_panio, 400)

    # Widget para configurar los paños del período seleccionado
    nuevo_panio_valor = col_sel_p2.number_input(
        f"✍️ Paños Realizados en {periodo_seleccionado.replace('📅 ', '')}:",
        min_value=1,
        value=int(panios_actuales),
        step=1,
        key=f"input_panio_{periodo_seleccionado}"
    )
    st.session_state.panios_por_mes[clave_panio] = nuevo_panio_valor
    panios_finales = nuevo_panio_valor

    costo_por_pano_calc = (consumo_insumos_sel / panios_finales) if panios_finales > 0 else 0.0

    st.markdown("### 📈 Indicadores Globales del Período")
    
    # Tarjetas KPI (Estilo idéntico a la captura)
    kpi1, kpi2, kpi3 = st.columns(3)
    
    with kpi1:
        st.metric(
            label="CONSUMO DE INSUMOS",
            value=formatear_precio(consumo_insumos_sel)
        )
    with kpi2:
        st.metric(
            label="PAÑOS REALIZADOS",
            value=f"{panios_finales:,}"
        )
    with kpi3:
        st.metric(
            label="COSTO PROMEDIO X PAÑO",
            value=formatear_precio(costo_por_pano_calc)
        )

    st.markdown("---")
    st.markdown("### 📋 Resumen Detallado de Todos los Meses Configurados")
    
    # Tabla consolidada con todos los meses que tengan datos o hayan sido tocados
    resumen_tabla_data = []
    meses_a_mostrar = set(list(gastos_salidas_por_mes.keys()) + [pd.Period(year=anio_actual, month=m, freq='M') for m in range(1, 13)])
    
    for per in sorted(list(meses_a_mostrar), reverse=True):
        m_nom = f"{MESES_ESPANOL[per.month].capitalize()} {per.year}"
        gasto_m = gastos_salidas_por_mes.get(per, 0.0)
        pan_m = st.session_state.panios_por_mes.get(m_nom, 400)
        costo_m = (gasto_m / pan_m) if pan_m > 0 else 0.0
        
        # Solo mostrar meses con gastos o que el usuario haya configurado explícitamente
        if gasto_m > 0 or m_nom in st.session_state.panios_por_mes:
            resumen_tabla_data.append({
                "Período / Mes": m_nom,
                "Consumo Insumos ($)": gasto_m,
                "Paños Realizados": pan_m,
                "Costo por Paño ($)": costo_m
            })

    if resumen_tabla_data:
        df_resumen_final = pd.DataFrame(resumen_tabla_data)
        st.dataframe(
            df_resumen_final,
            column_config={
                "Período / Mes": st.column_config.TextColumn("Período / Mes", disabled=True),
                "Consumo Insumos ($)": st.column_config.NumberColumn("Consumo Insumos ($)", format="$ %.2f", disabled=True),
                "Paños Realizados": st.column_config.NumberColumn("Paños Realizados", disabled=True),
                "Costo por Paño ($)": st.column_config.NumberColumn("Costo por Paño ($)", format="$ %.2f", disabled=True),
            },
            hide_index=True,
            use_container_width=True
        )
    else:
        st.info("No hay registros de salidas con montos para mostrar todavía.")
