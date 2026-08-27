import streamlit as st
import pandas as pd

st.set_page_config(page_title="Control de Insumos", page_icon="🎨", layout="wide")

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

# Cargamos datos globales
df_inventario_raw = cargar_datos("Inventario Insumos")
df_salida_raw = cargar_datos("salida")

# --- BARRA LATERAL (BOTÓN REFRESCAR + CONSULTA RÁPIDA DE STOCK) ---

if st.sidebar.button("🔄 Refrescar Datos", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

st.sidebar.header("🔍 Consulta Rápida de Stock")
if df_inventario_raw is not None:
    df_inv_sidebar = limpiar_tabla(df_inventario_raw)
    col_prod_inv = df_inv_sidebar.columns[1] if len(df_inv_sidebar.columns) > 1 else df_inv_sidebar.columns[0]
    col_stock_inv = next((c for c in df_inv_sidebar.columns if 'stock' in c.lower() or 'cantidad' in c.lower()), None)
    
    lista_productos = sorted(df_inv_sidebar[col_prod_inv].dropna().astype(str).unique().tolist())
    
    prod_seleccionado = st.sidebar.selectbox(
        "Buscar o seleccionar producto:", 
        options=lista_productos,
        index=None,
        placeholder="Escribí para buscar..."
    )
    
    if prod_seleccionado and col_stock_inv:
        cant = df_inv_sidebar[df_inv_sidebar[col_prod_inv] == prod_seleccionado][col_stock_inv].values
        if len(cant) > 0:
            st.sidebar.success(f"📦 **{prod_seleccionado}**\n\nStock Disponible: **{cant[0]} unidades**")

st.sidebar.markdown("---")
st.sidebar.header("⚙️ Filtros de Salida Mensual")

# --- CABECERA PRINCIPAL ---
st.title("🎨🛠️ Control de Insumos")

# Pestañas principales con 'Total Anual' al final
tab_ingreso, tab_salida, tab_reposicion, tab_diferencias, tab_inventario, tab_anual = st.tabs(
    ["📥 Ingresos", "📤 Salida", "🛒 Reposición", "⚠️ Diferencias", "📦 Inventario", "📅 Total Anual"]
)

# --- 1. PESTAÑA INGRESOS ---
with tab_ingreso:
    st.subheader("Registro de Ingreso de Insumos")
    df_ingreso = cargar_datos("ingresos")
    if df_ingreso is not None:
        df_ing_limpio = limpiar_tabla(df_ingreso)
        if 'fecha' in [c.lower() for c in df_ing_limpio.columns]:
            df_ing_limpio['fecha'] = df_ing_limpio['fecha'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_ing_limpio, use_container_width=True, hide_index=True)

# --- 2. PESTAÑA SALIDA ---
with tab_salida:
    st.subheader("📊 Consulta de Salidas por Técnico y Mes")
    
    if df_salida_raw is not None:
        df_sal_limpio = limpiar_tabla(df_salida_raw)
        
        col_fecha = next((c for c in df_sal_limpio.columns if 'fecha' in str(c).lower()), None)
        col_nombre = next((c for c in df_sal_limpio.columns if any(k in str(c).lower() for k in ['nombre', 'tecnico', 'técnico', 'operario'])), None)
        col_cant = next((c for c in df_sal_limpio.columns if 'cantidad' in str(c).lower()), None)
        col_b = df_sal_limpio.columns[1] if len(df_sal_limpio.columns) > 1 else None
        
        if col_fecha and col_nombre:
            meses_espanol = {1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril", 5:"Mayo", 6:"Junio", 
                            7:"Julio", 8:"Agosto", 9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"}
            
            df_sal_limpio['Mes_Num'] = df_sal_limpio[col_fecha].dt.month
            df_sal_limpio['Nombre_Mes'] = df_sal_limpio['Mes_Num'].map(meses_espanol)
            
            lista_meses = ["Todos"] + [m for m in meses_espanol.values() if m in df_sal_limpio['Nombre_Mes'].unique()]
            mes_seleccionado = st.sidebar.selectbox("🗓️ Seleccionar Mes:", lista_meses)
            
            nombres_unicos = df_sal_limpio[col_nombre].dropna().astype(str).str.strip().unique()
            lista_tecnicos = ["Todos"] + sorted(list(nombres_unicos))
            tecnico_seleccionado = st.sidebar.selectbox("👷 Seleccionar Técnico / Nombre:", lista_tecnicos)
            
            # Filtrado
            df_filtrado = df_sal_limpio.copy()
            
            if mes_seleccionado != "Todos":
                df_filtrado = df_filtrado[df_filtrado['Nombre_Mes'] == mes_seleccionado]
                
            if tecnico_seleccionado != "Todos":
                patron = tecnico_seleccionado.strip().lower()
                df_filtrado = df_filtrado[
                    df_filtrado[col_nombre].astype(str).str.strip().str.lower().str.contains(patron, regex=False, na=False)
                ]

            # Tarjetas de totales
            if not df_filtrado.empty and col_cant:
                total_unidades = int(df_filtrado[col_cant].sum())
                tipos_distintos = df_filtrado[col_b].nunique() if col_b else len(df_filtrado)
                total_registros = len(df_filtrado)

                c1, c2, c3 = st.columns(3)
                c1.metric("🔢 Total Insumos Entregados", f"{total_unidades} unidades")
                c2.metric("📦 Variedad de Productos", f"{tipos_distintos} ítems")
                c3.metric("📋 Registros de Salida", f"{total_registros} movimientos")

                st.markdown("---")

            # Tabla acumulada
            st.markdown("### 🧮 Total Acumulado por Insumo")
            
            if not df_filtrado.empty and col_cant:
                cols_agrupar = [c for c in df_filtrado.columns if c not in [col_fecha, col_nombre, col_cant, 'Mes_Num', 'Nombre_Mes']]
                if cols_agrupar:
                    df_resumen = df_filtrado.groupby(cols_agrupar, as_index=False)[col_cant].sum()
                    
                    fila_total = {col: "" for col in df_resumen.columns}
                    fila_total[cols_agrupar[0]] = "TOTAL GENERAL"
                    fila_total[col_cant] = total_unidades
                    
                    df_resumen_con_total = pd.concat([df_resumen, pd.DataFrame([fila_total])], ignore_index=True)
                    st.dataframe(df_resumen_con_total, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(df_filtrado, use_container_width=True, hide_index=True)
            else:
                st.warning("No hay registros de salidas para la selección actual.")

            # Historial detallado
            st.markdown("---")
            st.markdown("### 📋 Historial Detallado de Registros")
            
            if not df_filtrado.empty:
                df_vista = df_filtrado.copy()
                df_vista[col_fecha] = df_vista[col_fecha].dt.strftime('%Y-%m-%d')
                df_vista = df_vista.drop(columns=['Mes_Num', 'Nombre_Mes'], errors='ignore')
                st.dataframe(df_vista, use_container_width=True, hide_index=True)

            # Gráfico ordenado
            if col_b and col_cant and not df_filtrado.empty:
                st.markdown("---")
                st.markdown(f"### 📈 Consumo de Insumos por {col_b} (De Mayor a Menor)")
                
                df_grafico = df_filtrado.groupby(col_b, as_index=False)[col_cant].sum()
                df_grafico = df_grafico.sort_values(by=col_cant, ascending=False).reset_index(drop=True)
                
                df_grafico[col_b] = pd.Categorical(
                    df_grafico[col_b], 
                    categories=df_grafico[col_b].tolist(), 
                    ordered=True
                )
                
                st.bar_chart(data=df_grafico, x=col_b, y=col_cant, use_container_width=True)

# --- 3. PESTAÑA REPOSICIÓN ---
with tab_reposicion:
    st.subheader("Lista de Compras / Faltantes")
    if df_inventario_raw is not None:
        df_inv_limpio = limpiar_tabla(df_inventario_raw, mantener_dif=False)
        col_estado = 'Estado' if 'Estado' in df_inv_limpio.columns else ('estado' if 'estado' in df_inv_limpio.columns else None)
        if col_estado:
            df_reponer = df_inv_limpio[df_inv_limpio[col_estado].str.strip().str.upper() == 'REPONER']
            st.info(f"💡 Tenés {len(df_reponer)} artículos en tu lista de compras.")
            st.dataframe(df_reponer.style.map(aplicar_estilos, subset=[col_estado]), use_container_width=True, hide_index=True)

# --- 4. PESTAÑA DIFERENCIAS ---
with tab_diferencias:
    st.subheader("⚠️ Reporte de Diferencias e Inconsistencias")
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

# --- 5. PESTAÑA INVENTARIO ---
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

        busqueda = st.text_input("🔍 Buscar insumo en tabla (por nombre, código, marca o medida):", "")
        
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

# --- 6. PESTAÑA TOTAL ANUAL (AL FINAL) ---
with tab_anual:
    st.subheader("📅 Resumen Anual y Evolución Mes a Mes")
    
    if df_salida_raw is not None:
        df_sal_limpio = limpiar_tabla(df_salida_raw)
        
        col_fecha = next((c for c in df_sal_limpio.columns if 'fecha' in str(c).lower()), None)
        col_nombre = next((c for c in df_sal_limpio.columns if any(k in str(c).lower() for k in ['nombre', 'tecnico', 'técnico', 'operario'])), None)
        col_cant = next((c for c in df_sal_limpio.columns if 'cantidad' in str(c).lower()), None)
        col_producto = df_sal_limpio.columns[1] if len(df_sal_limpio.columns) > 1 else None

        if col_fecha and col_cant:
            meses_espanol = {1:"Enero", 2:"Febrero", 3:"Marzo", 4:"Abril", 5:"Mayo", 6:"Junio", 
                            7:"Julio", 8:"Agosto", 9:"Septiembre", 10:"Octubre", 11:"Noviembre", 12:"Diciembre"}
            
            df_sal_limpio['Mes_Num'] = df_sal_limpio[col_fecha].dt.month

            tipo_vista = st.radio("Ver resumen anual por:", ["📦 Consumo por Insumo/Producto", "👷 Consumo por Técnico"], horizontal=True)

            if "Insumo" in tipo_vista and col_producto:
                pivot_df = pd.pivot_table(
                    df_sal_limpio, 
                    values=col_cant, 
                    index=[col_producto], 
                    columns=['Mes_Num'], 
                    aggfunc='sum', 
                    fill_value=0
                )
                pivot_df.rename(columns=meses_espanol, inplace=True)
                pivot_df['Total Anual'] = pivot_df.sum(axis=1)
                pivot_df = pivot_df.sort_values(by='Total Anual', ascending=False)
                
                # Formatear a números enteros limpios
                pivot_df = pivot_df.astype(int)
                st.dataframe(pivot_df, use_container_width=True)

            elif "Técnico" in tipo_vista and col_nombre:
                pivot_df = pd.pivot_table(
                    df_sal_limpio, 
                    values=col_cant, 
                    index=[col_nombre], 
                    columns=['Mes_Num'], 
                    aggfunc='sum', 
                    fill_value=0
                )
                pivot_df.rename(columns=meses_espanol, inplace=True)
                pivot_df['Total Anual'] = pivot_df.sum(axis=1)
                pivot_df = pivot_df.sort_values(by='Total Anual', ascending=False)
                
                # Formatear a números enteros limpios
                pivot_df = pivot_df.astype(int)
                st.dataframe(pivot_df, use_container_width=True)
