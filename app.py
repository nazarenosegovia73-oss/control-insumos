import streamlit as st
import pandas as pd

st.set_page_config(page_title="Gestión de Insumos", layout="wide")

st.title("🚗 Control y Gestión de Insumos")

URL_BASE = "https://docs.google.com/spreadsheets/d/1FTfpL-EXH2sAKpW4Y65lyEJeiTeTWFCX/export?format=xlsx"

@st.cache_data(ttl=60)
def cargar_datos(nombre_hoja):
    try:
        df = pd.read_excel(URL_BASE, sheet_name=nombre_hoja)
        return df
    except Exception as e:
        st.error(f"No se pudo cargar la hoja '{nombre_hoja}'. Verificá que el nombre en Drive sea exacto.")
        return None

def limpiar_tabla(df, mantener_dif=False):
    if df is None or df.empty:
        return df
    
    columnas_a_borrar = ['categoría', 'categoria', 'real', 'stok inicial', 'stock inicial']
    if not mantener_dif:
        columnas_a_borrar.append('dif')

    cols_a_eliminar = [
        col for col in df.columns 
        if str(col).strip().lower() in columnas_a_borrar or 'unnamed' in str(col).lower()
    ]
    df_limpio = df.drop(columns=cols_a_eliminar, errors='ignore')
    
    for col in df_limpio.columns:
        col_lower = str(col).lower()
        if 'fecha' in col_lower:
            df_limpio[col] = pd.to_datetime(df_limpio[col], errors='coerce')
        elif any(k in col_lower for k in ['stock', 'cantidad', 'minimo', 'mínimo', 'dif']):
            df_limpio[col] = pd.to_numeric(df_limpio[col], errors='coerce').fillna(0).astype(int)
            
    return df_limpio

def aplicar_estilos(val):
    if str(val).strip().upper() == 'OK':
        return 'background-color: #d4edda; color: #155724; font-weight: bold;'
    elif str(val).strip().upper() == 'REPONER':
        return 'background-color: #f8d7da; color: #721c24; font-weight: bold;'
    return ''

# Pestañas principales
tab_inventario, tab_reposicion, tab_diferencias, tab_ingreso, tab_salida = st.tabs(
    ["📦 Inventario", "🛒 Reposición", "⚠️ Diferencias", "📥 Ingresos", "📤 Salida"]
)

# Cargamos el inventario base
df_inventario_raw = cargar_datos("Inventario Insumos")

# --- PESTAÑA INVENTARIO ---
with tab_inventario:
    if df_inventario_raw is not None:
        df_inv_limpio = limpiar_tabla(df_inventario_raw, mantener_dif=False)
        col_estado = 'Estado' if 'Estado' in df_inv_limpio.columns else ('estado' if 'estado' in df_inv_limpio.columns else None)

        total_items = len(df_inv_limpio)
        ok_items = len(df_inv_limpio[df_inv_limpio[col_estado].str.strip().str.upper() == 'OK']) if col_estado else 0
        reponer_items = len(df_inv_limpio[df_inv_limpio[col_estado].str.strip().str.upper() == 'REPONER']) if col_estado else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("📦 Total Insumos", total_items)
        col2.metric("✅ En Stock (OK)", ok_items)
        col3.metric("⚠️ A Reponer", reponer_items, delta_color="inverse")

        st.markdown("---")

        busqueda = st.text_input("🔍 Buscar insumo (por nombre, código, marca o medida):", "")
        
        if 'fecha' in [c.lower() for c in df_inv_limpio.columns]:
            df_inv_limpio['fecha'] = df_inv_limpio['fecha'].dt.strftime('%Y-%m-%d')

        if busqueda:
            mascara = df_inv_limpio.astype(str).apply(lambda x: x.str.contains(busqueda, case=False, na=False)).any(axis=1)
            df_mostrar = df_inv_limpio[mascara]
        else:
            df_mostrar = df_inv_limpio

        if col_estado:
            st.dataframe(df_mostrar.style.map(aplicar_estilos, subset=[col_estado]), use_container_width=True, hide_index=True)
        else:
            st.dataframe(df_mostrar, use_container_width=True, hide_index=True)

# --- PESTAÑA REPOSICIÓN ---
with tab_reposicion:
    st.subheader("Lista de Compras / Faltantes")
    if df_inventario_raw is not None:
        df_inv_limpio = limpiar_tabla(df_inventario_raw, mantener_dif=False)
        col_estado = 'Estado' if 'Estado' in df_inv_limpio.columns else ('estado' if 'estado' in df_inv_limpio.columns else None)
        if col_estado:
            df_reponer = df_inv_limpio[df_inv_limpio[col_estado].str.strip().str.upper() == 'REPONER']
            st.info(f"💡 Tenés {len(df_reponer)} artículos en tu lista de compras.")
            st.dataframe(df_reponer.style.map(aplicar_estilos, subset=[col_estado]), use_container_width=True, hide_index=True)

# --- PESTAÑA DIFERENCIAS ---
with tab_diferencias:
    st.subheader("⚠️ Reporte de Diferencias y Inconsistencias")
    if df_inventario_raw is not None:
        df_dif = limpiar_tabla(df_inventario_raw, mantener_dif=True)
        col_dif = next((col for col in df_dif.columns if str(col).lower() in ['dif', 'diferencia']), None)
        
        if col_dif:
            df_errores = df_dif[df_dif[col_dif] < 0]
            if not df_errores.empty:
                st.warning(f"Se encontraron **{len(df_errores)}** insumos con diferencias o faltantes negativos.")
                st.dataframe(df_errores, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 ¡Excelente! No hay diferencias o valores negativos registrados.")

# --- PESTAÑA INGRESOS ---
with tab_ingreso:
    st.subheader("Registro de Ingreso de Insumos")
    df_ingreso = cargar_datos("ingresos")
    if df_ingreso is not None:
        df_ing_limpio = limpiar_tabla(df_ingreso)
        if 'fecha' in [c.lower() for c in df_ing_limpio.columns]:
            df_ing_limpio['fecha'] = df_ing_limpio['fecha'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_ing_limpio, use_container_width=True, hide_index=True)

# --- PESTAÑA SALIDA CON CONSOLIDADO DE TOTALES ---
with tab_salida:
    st.subheader("📊 Consulta de Salidas por Técnico y Mes")
    df_salida = cargar_datos("salida")
    
    if df_salida is not None:
        df_sal_limpio = limpiar_tabla(df_salida)
        
        col_fecha = next((c for c in df_sal_limpio.columns if 'fecha' in c.lower()), None)
        col_nombre = next((c for c in df_sal_limpio.columns if 'nombre' in c.lower() or 'tecnico' in c.lower() or 'técnico' in c.lower()), None)
        col_cant = next((c for c in df_sal_limpio.columns if 'cantidad' in c.lower()), None)
        
        if col_fecha and col_nombre:
            meses_espanol = {1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril", 5:"Mayo", 6:"Junio", 
                            7:"Julio", 8:"Agosto", 9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"}
            
            df_sal_limpio['Mes_Num'] = df_sal_limpio[col_fecha].dt.month
            df_sal_limpio['Nombre_Mes'] = df_sal_limpio['Mes_Num'].map(meses_espanol)
            
            f_col1, f_col2 = st.columns(2)
            
            lista_meses = ["Todos"] + [m for m in meses_espanol.values() if m in df_sal_limpio['Nombre_Mes'].unique()]
            mes_seleccionado = f_col1.selectbox("🗓️ Seleccionar Mes:", lista_meses)
            
            lista_tecnicos = ["Todos"] + sorted(list(df_sal_limpio[col_nombre].dropna().unique()))
            tecnico_seleccionado = f_col2.selectbox("👷 Seleccionar Técnico / Nombre:", lista_tecnicos)
            
            # Filtro
            df_filtrado = df_sal_limpio.copy()
            if mes_seleccionado != "Todos":
                df_filtrado = df_filtrado[df_filtrado['Nombre_Mes'] == mes_seleccionado]
            if tecnico_seleccionado != "Todos":
                df_filtrado = df_filtrado[df_filtrado[col_nombre] == tecnico_seleccionado]

            # --- TABLA CONSOLIDADA (TOTALES SUMADOS) ---
            st.markdown("### 🧮 Total Acumulado por Insumo")
            cols_agrupar = [c for c in df_filtrado.columns if c not in [col_fecha, col_nombre, col_cant, 'Mes_Num', 'Nombre_Mes']]
            
            if cols_agrupar and col_cant:
                df_resumen = df_filtrado.groupby(cols_agrupar, as_index=False)[col_cant].sum()
                st.dataframe(df_resumen, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("### 📋 Historial Detallado de Registros")
            
            df_vista = df_filtrado.copy()
            df_vista[col_fecha] = df_vista[col_fecha].dt.strftime('%Y-%m-%d')
            df_vista = df_vista.drop(columns=['Mes_Num', 'Nombre_Mes'], errors='ignore')
            st.dataframe(df_vista, use_container_width=True, hide_index=True)
            
        else:
            st.warning("No se encontraron las columnas 'fecha' o 'nombre' en la hoja de salida.")
