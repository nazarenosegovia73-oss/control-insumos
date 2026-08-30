import streamlit as st
import pandas as pd
import re
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="Control de Insumos", page_icon="🎨", layout="wide")

ID_SHEET = "1cJ6FH-lJWn52UzhMRAEhpIZ-FRcdfJNzwYtouAQE0CE"
URL_BASE = f"https://docs.google.com/spreadsheets/d/{ID_SHEET}/export?format=xlsx"
RUTA_CREDANCIALES = "credenciales.json"

def obtener_cliente_gspread():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        
        # Intenta leer desde los Secretos de Streamlit Cloud
        if "gcp_service_account" in st.secrets:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        else:
            # Si estás probando localmente en tu PC
            creds = ServiceAccountCredentials.from_json_keyfile_name(RUTA_CREDANCIALES, scope)
            
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        return None

@st.cache_data(ttl=10)
def cargar_datos(nombre_hoja):
    try:
        df = pd.read_excel(URL_BASE, sheet_name=nombre_hoja)
        return df
    except Exception as e:
        st.error(f"No se pudo cargar la hoja '{nombre_hoja}'. Verificá el nombre exacto.")
        return None

def limpiar_texto(texto):
    if pd.isna(texto):
        return ""
    txt = str(texto).strip().lower()
    return re.sub(r'\s+', ' ', txt)

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
            df_limpio[col] = pd.to_datetime(df_limpio[col], errors='coerce', dayfirst=True)
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

df_inventario_raw = cargar_datos("Inventario Insumos")
df_salida_raw = cargar_datos("salida")
df_ingreso_raw = cargar_datos("ingresos")

if st.sidebar.button("🔄 Refrescar Datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.header("🔍 Consulta Rápida de Stock")
if df_inventario_raw is not None:
    df_inv_sidebar = limpiar_tabla(df_inventario_raw)
    col_prod_inv = df_inv_sidebar.columns[1] if len(df_inv_sidebar.columns) > 1 else df_inv_sidebar.columns[0]
    col_stock_inv = next((c for c in df_inv_sidebar.columns if 'stock' in c.lower() or 'cantidad' in c.lower()), None)
    
    lista_productos = sorted([p for p in df_inv_sidebar[col_prod_inv].unique().tolist() if str(p).strip()])
    prod_seleccionado = st.sidebar.selectbox("Buscar o seleccionar producto:", options=lista_productos, index=None, placeholder="Escribí para buscar...")
    
    if prod_seleccionado and col_stock_inv:
        cant = df_inv_sidebar[df_inv_sidebar[col_prod_inv] == prod_seleccionado][col_stock_inv].values
        if len(cant) > 0:
            st.sidebar.success(f"📦 **{prod_seleccionado}**\n\nStock Disponible: **{cant[0]} unidades**")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Filtros para Salida")

filtro_mes = "Todos"
filtro_tecnico = "Todos"

if df_salida_raw is not None:
    df_salida_filtros = limpiar_tabla(df_salida_raw)
    col_fecha_s = next((c for c in df_salida_filtros.columns if 'fecha' in str(c).lower()), None)
    col_tec_s = next((c for c in df_salida_filtros.columns if any(k in str(c).lower() for k in ['tecnico', 'técnico', 'retira', 'operario', 'persona'])), None)

    if col_fecha_s:
        df_salida_filtros['AñoMes'] = pd.to_datetime(df_salida_filtros[col_fecha_s], errors='coerce').dt.to_period('M').astype(str)
        meses_disponibles = ["Todos"] + sorted([m for m in df_salida_filtros['AñoMes'].unique().tolist() if m and m != 'NaT'], reverse=True)
        filtro_mes = st.sidebar.selectbox("📅 Seleccionar Mes (Salida):", options=meses_disponibles)

    if col_tec_s:
        tecnicos_disponibles = ["Todos"] + sorted([t for t in df_salida_filtros[col_tec_s].unique().tolist() if str(t).strip()])
        filtro_tecnico = st.sidebar.selectbox("👷 Seleccionar Técnico (Salida):", options=tecnicos_disponibles)

st.title("🎨🛠️ Control de Insumos")

tab_ingreso, tab_salida, tab_reposicion, tab_diferencias, tab_inventario, tab_indicadores = st.tabs(
    ["📥 Ingresos", "📤 Salida", "🛒 Reposición", "⚠️ Diferencias", "📦 Inventario", "📊 Indicadores"]
)

if "lista_ingresos_pendientes" not in st.session_state:
    st.session_state.lista_ingresos_pendientes = []

# --- PESTAÑA INGRESOS ---
with tab_ingreso:
    st.subheader("📝 Carga Rápida de Insumos")
    
    if df_inventario_raw is not None and len(df_inventario_raw.columns) >= 3:
        opciones_prods_col_c = sorted([p for p in df_inventario_raw.iloc[:, 2].dropna().astype(str).str.strip().unique().tolist() if p and p != "0" and p.lower() != "nan"])
    else:
        opciones_prods_col_c = []

    opciones_proveedores = []
    if df_ingreso_raw is not None:
        col_prov_ing = next((c for c in df_ingreso_raw.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'donde', 'comprado', 'local', 'vendedor'])), None)
        if col_prov_ing:
            lista_provs = df_ingreso_raw[col_prov_ing].dropna().astype(str).str.strip().unique().tolist()
            opciones_proveedores = sorted([p for p in lista_provs if p != "" and p != "0" and p.lower() != "nan"])

    with st.form("form_agregar_item", clear_on_submit=True):
        col_prod, col_fecha = st.columns([3, 1])
        producto_ingresado = col_prod.selectbox("📦 Producto / Detalle *", options=opciones_prods_col_c, index=None, placeholder="Seleccioná o escribí para buscar...")
        fecha_ingreso = col_fecha.date_input("📅 Fecha de Compra *", value=datetime.date.today())
        
        col_cant, col_precio, col_prov = st.columns([1, 1, 2])
        cantidad_ingresada = col_cant.number_input("🔢 Cantidad *", min_value=1, value=1, step=1)
        precio_ingresado = col_precio.number_input("💵 Precio Unitario ($) *", min_value=0.0, value=0.0, step=100.0)
        
        prov_seleccionado = col_prov.selectbox("🏢 Proveedor habitual *", options=opciones_proveedores, index=None, placeholder="Seleccioná un proveedor...")
        nuevo_prov_escrito = st.text_input("➕ O escribí un nuevo proveedor aquí:", placeholder="Ej: Wurth Argentina").strip()

        proveedor_final = nuevo_prov_escrito if nuevo_prov_escrito else prov_seleccionado

        btn_agregar = st.form_submit_button("➕ Agregar a la Lista de Carga", type="secondary", use_container_width=True)

        if btn_agregar:
            errores = []
            if not producto_ingresado:
                errores.append("Producto / Detalle")
            if cantidad_ingresada <= 0:
                errores.append("Cantidad")
            if precio_ingresado <= 0:
                errores.append("Precio Unitario")
            if not proveedor_final:
                errores.append("Proveedor")

            if errores:
                st.error(f"⚠️ **Faltan campos:** {', '.join(errores)}")
            else:
                articulo_val = ""
                categoria_val = ""
                marca_val = ""
                medida_val = ""
                
                if df_inventario_raw is not None and len(df_inventario_raw.columns) >= 5:
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
                    "Fecha": fecha_ingreso.strftime("%d-%m"),
                    "Precio Unitario": precio_ingresado,
                    "Precio Total": cantidad_ingresada * precio_ingresado,
                    "Proveedor": proveedor_final
                })
                st.toast(f"➕ Agregado a la lista: {producto_ingresado}")
                st.rerun()

    st.markdown("---")
    
    if st.session_state.lista_ingresos_pendientes:
        st.subheader("🛒 Insumos Pendientes de Guardar")
        df_pendientes = pd.DataFrame(st.session_state.lista_ingresos_pendientes)
        
        df_editado = st.data_editor(
            df_pendientes,
            num_rows="dynamic",
            use_container_width=True,
            key="editor_ingresos_pendientes"
        )

        col_guardar, col_limpiar = st.columns([3, 1])
        
        if col_guardar.button("💾 Guardar TODO en Google Sheets", type="primary", use_container_width=True):
            client = obtener_cliente_gspread()
            if client is None:
                st.error("❌ No se pudo conectar a Google Sheets. Verificá las credenciales.")
            else:
                try:
                    sheet_ingresos = client.open_by_key(ID_SHEET).worksheet("ingresos")
                    col_c_valores = sheet_ingresos.col_values(3)
                    primera_fila_vacia = len(col_c_valores) + 1
                    
                    filas_a_subir = df_editado.values.tolist()
                    filas_nuevas = len(filas_a_subir)
                    ultima_fila = primera_fila_vacia + filas_nuevas - 1
                    
                    rango_insertar = f"A{primera_fila_vacia}:J{ultima_fila}"
                    sheet_ingresos.update(rango_insertar, filas_a_subir)
                    
                    st.success(f"✅ ¡Se guardaron {filas_nuevas} registros en Google Sheets!")
                    st.session_state.lista_ingresos_pendientes = []
                    st.cache_data.clear()
                    st.rerun()
                except Exception as err:
                    st.error(f"❌ Error al escribir en Google Sheets: {err}")

        if col_limpiar.button("🗑️ Cancelar Lista", use_container_width=True):
            st.session_state.lista_ingresos_pendientes = []
            st.rerun()

    st.markdown("---")
    st.subheader("📋 Registro de Ingreso de Insumos (Histórico)")
    
    if df_ingreso_raw is not None:
        df_ing_limpio = limpiar_tabla(df_ingreso_raw)
        col_fecha_ing = next((c for c in df_ing_limpio.columns if 'fecha' in str(c).lower()), None)
        col_prod_ing = next((c for c in df_ing_limpio.columns if any(k in str(c).lower() for k in ['producto', 'insumo', 'detalle', 'descripcion'])), df_ing_limpio.columns[1] if len(df_ing_limpio.columns) > 1 else df_ing_limpio.columns[0])
        col_precio_ing = next((c for c in df_ing_limpio.columns if any(k in str(c).lower() for k in ['precio unitario', 'precio', 'costo', 'valor'])), None)
        col_prov_ing = next((c for c in df_ing_limpio.columns if any(k in str(c).lower() for k in ['proovedor', 'proveedor', 'lugar', 'donde', 'comprado', 'compras', 'local', 'vendedor'])), None)

        if col_fecha_ing:
            df_ing_vista = df_ing_limpio.copy()
            df_ing_vista[col_fecha_ing] = pd.to_datetime(df_ing_vista[col_fecha_ing], errors='coerce').dt.strftime('%Y-%m-%d')
            st.dataframe(df_ing_vista, use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_ing_limpio, use_container_width=True, hide_index=True)

        if col_fecha_ing and col_prod_ing and col_precio_ing:
            st.markdown("---")
            st.subheader("📈 Análisis de Aumento de Precios Mes a Mes")
            
            df_precios = df_ing_limpio.dropna(subset=[col_fecha_ing, col_prod_ing, col_precio_ing]).copy()
            df_precios[col_precio_ing] = pd.to_numeric(df_precios[col_precio_ing], errors='coerce').fillna(0)
            df_precios = df_precios[df_precios[col_precio_ing] > 0]

            if not df_precios.empty:
                df_precios['Periodo'] = pd.to_datetime(df_precios[col_fecha_ing], errors='coerce').dt.to_period('M')
                df_precios['Mes'] = df_precios['Periodo'].astype(str)

                if col_prov_ing:
                    df_precios[col_prov_ing] = df_precios[col_prov_ing].replace("", "Sin Especificar").astype(str).str.strip().str.capitalize()

                resumen_variacion = []
                df_ordenado = df_precios.sort_values(by=col_fecha_ing)

                for prod, group in df_ordenado.groupby(col_prod_ing):
                    if len(group) >= 2:
                        p_inicial = group.iloc[0][col_precio_ing]
                        p_final = group.iloc[-1][col_precio_ing]
                        f_inicial = pd.to_datetime(group.iloc[0][col_fecha_ing]).strftime('%d/%m/%Y')
                        f_final = pd.to_datetime(group.iloc[-1][col_fecha_ing]).strftime('%d/%m/%Y')
                        prov_ini = group.iloc[0][col_prov_ing] if col_prov_ing else "-"
                        prov_fin = group.iloc[-1][col_prov_ing] if col_prov_ing else "-"

                        if p_inicial > 0:
                            var_pct = ((p_final - p_inicial) / p_inicial) * 100
                            dif_abs = p_final - p_inicial
                            resumen_variacion.append({
                                'Producto': prod,
                                'Fecha Inicial': f_inicial,
                                'Proveedor Inicial': prov_ini,
                                'Precio Inicial': p_inicial,
                                'Última Fecha': f_final,
                                'Último Proveedor': prov_fin,
                                'Precio Actual': p_final,
                                'Diferencia ($)': dif_abs,
                                '% Aumento': var_pct
                            })

                df_var = pd.DataFrame(resumen_variacion)
                if not df_var.empty:
                    st.markdown("### 🔥 Top Insumos que MÁS Aumentaron")
                    df_mas_aum = df_var[df_var['% Aumento'] > 0].sort_values(by='% Aumento', ascending=False)
                    if not df_mas_aum.empty:
                        df_mas_aum_vista = df_mas_aum.copy()
                        df_mas_aum_vista['Precio Inicial'] = df_mas_aum_vista['Precio Inicial'].apply(lambda x: f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        df_mas_aum_vista['Precio Actual'] = df_mas_aum_vista['Precio Actual'].apply(lambda x: f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        df_mas_aum_vista['Diferencia ($)'] = df_mas_aum_vista['Diferencia ($)'].apply(lambda x: f"${x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
                        df_mas_aum_vista['% Aumento'] = df_mas_aum_vista['% Aumento'].apply(lambda x: f"+{x:.1f}%")
                        st.dataframe(df_mas_aum_vista, use_container_width=True, hide_index=True)

# --- PESTAÑA SALIDA ---
with tab_salida:
    st.subheader("📤 Registro de Salida de Insumos")
    if df_salida_raw is not None:
        df_sal_limpio = limpiar_tabla(df_salida_raw)
        
        col_fecha_s = next((c for c in df_sal_limpio.columns if 'fecha' in str(c).lower()), None)
        col_tec_s = next((c for c in df_sal_limpio.columns if any(k in str(c).lower() for k in ['tecnico', 'técnico', 'retira', 'operario', 'persona'])), None)

        if col_fecha_s and filtro_mes != "Todos":
            df_sal_limpio['AñoMes'] = pd.to_datetime(df_sal_limpio[col_fecha_s], errors='coerce').dt.to_period('M').astype(str)
            df_sal_limpio = df_sal_limpio[df_sal_limpio['AñoMes'] == filtro_mes].drop(columns=['AñoMes'])

        if col_tec_s and filtro_tecnico != "Todos":
            df_sal_limpio = df_sal_limpio[df_sal_limpio[col_tec_s].astype(str) == filtro_tecnico]

        if col_fecha_s:
            df_sal_limpio[col_fecha_s] = pd.to_datetime(df_sal_limpio[col_fecha_s], errors='coerce').dt.strftime('%Y-%m-%d')

        st.dataframe(df_sal_limpio, use_container_width=True, hide_index=True)

# --- PESTAÑA REPOSICIÓN ---
with tab_reposicion:
    st.subheader("🛒 Estado de Reposición de Stock")
    if df_inventario_raw is not None:
        df_rep = limpiar_tabla(df_inventario_raw)
        if 'ESTADO' in df_rep.columns:
            st.dataframe(df_rep.style.map(aplicar_estilos, subset=['ESTADO']), use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_rep, use_container_width=True, hide_index=True)

# --- PESTAÑA DIFERENCIAS ---
with tab_diferencias:
    st.subheader("⚠️ Registro de Diferencias de Insumos")
    if df_inventario_raw is not None:
        st.dataframe(limpiar_tabla(df_inventario_raw, mantener_dif=True), use_container_width=True, hide_index=True)

# --- PESTAÑA INVENTARIO ---
with tab_inventario:
    st.subheader("📦 Inventario General de Insumos")
    if df_inventario_raw is not None:
        st.dataframe(limpiar_tabla(df_inventario_raw), use_container_width=True, hide_index=True)

# --- PESTAÑA INDICADORES ---
with tab_indicadores:
    st.subheader("📊 Indicadores Generales")
    st.info("Pestaña en desarrollo para métricas consolidadas.")
