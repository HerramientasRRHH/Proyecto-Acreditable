import sys
sys.path.insert(0, r'C:\Users\agutierrez\Desktop\Proyectos\Proyecto Acreditable\.claude\skills\acreditable-review\scripts')
from audit_antofagasta import get_pdf_text_ocr, find_all_ruts, find_all_ruts_raw, match_rut_cercano, cargar_lh, norm_rut
import os

base = r'C:\Users\agutierrez\Desktop\Proyectos\Proyecto Acreditable\Documentos Antofagasta\H).-Finiquitos - Seguro Cesantia - Contratos - Liquidaciones\liquidaciones'

casos_por_archivo = {
    'A. liquidación letra A.pdf': [('6.305.214-0','Araya Araya Victor Hugo'),('8.559.961-5','Araya Barraza David Antonio')],
    'C. liquidaciones letra C.pdf': [('23.162.740-5','Correa Castañeda Nila'),('25.797.456-1','Cuero Asprilla Maria Enith')],
    'D. liquidaciones letra D.pdf': [('26.426.053-1','Duran Ragua Jose Javier'),('13.191.732-5','De La Cruz Pacheco Hector Pascual Eugenio')],
    'E. liquidaciones letra E y F.pdf': [('5.859.211-0','Fredes Jeraldo Ana Maria')],
    'G. liquidaciones letra G.pdf': [('20.543.463-1','Gahona Zaragoza Marco Nicanor'),('13.357.030-6','Gutierrez Araya Evelyn Marcela'),('21.735.599-0','Gahona Zaragoza Mauricio Nicolas'),('12.610.974-1','Guzman Morales Teresa Isolina'),('13.867.833-4','Gallardo Pinto Jessica Diana')],
    'M. liquidaciones letra M.pdf': [('25.600.854-8','Muñoz Velez Yuced Alexis'),('28.982.236-4','Medina Paredes Marcos'),('10.894.899-k','Morales Vargas Domingo Segundo'),('12.613.084-8','Marin Miranda Jose Manuel'),('24.608.704-0','Mosquera Quiñones Kelly Xilena')],
    'O. liquidaciones letra O.pdf': [('29.131.524-0','Ovando Subia Juan Luis')],
    'P. Liquidaciones letra P.pdf': [('13.649.071-0','Pizarro Alvarez Cristian Alamiro'),('25.758.455-0','Polo Chavez Maribel'),('12.214.513-1','Parra Pasten Patricia'),('28.682.481-1','Pacosillo  Mirian Jeanette')],
    'R. liquidaciones leta R.pdf': [('25.530.716-9','Riascos Hurtado Julio Alberto'),('28.980.298-3','Rivera Angelo Eusebia'),('24.442.380-9','Rojas Zarate Noemi Abigail'),('24.292.008-2','Romero Mosquera Lludi Amparo')],
    'S. liquidaciones letra S.pdf': [('27.855.596-8','Salazar Mondragon Carlos Alberto'),('24.059.843-4','Seballo Moscoso Filandia Carmen'),('6.422.552-9','Salinas Menchaca Rafael Luis'),('28.632.937-3','Segovia Laura Maily'),('10.652.096-8','Segovia Salazar Andres'),('25.713.010-k','Sevillano Zelada Serafina')],
    'T. liquidaciones letra T.pdf': [('17.939.062-0','Tapia Colome Margarita Haydee')],
    'liquidaciones letra L.pdf': [('25.855.827-8','Landazuri Cuero Mary Santos')],
}

rows = cargar_lh(r'C:\Users\agutierrez\Downloads\2026-08-17 Libro de haberes Revisión Nuevo 2026-07-01.xlsx')
lh_ruts = [x['rutNorm'] for x in rows]

resueltos = []
no_resueltos = []

for archivo, casos in casos_por_archivo.items():
    path = os.path.join(base, archivo)
    print(f'=== procesando {archivo} ===', flush=True)
    txt, total = get_pdf_text_ocr(path, max_pages_ocr=100, verbose=False)
    raw = find_all_ruts_raw(txt)
    for rut, nombre in casos:
        rn = norm_rut(rut)
        rescatado = None
        for c in raw:
            m = match_rut_cercano(c, lh_ruts)
            if m == rn:
                rescatado = m
                break
        if rescatado:
            resueltos.append((rut, nombre))
            print(f'  RESUELTO: {nombre} ({rut})', flush=True)
        else:
            no_resueltos.append((rut, nombre))
            print(f'  NO resuelto: {nombre} ({rut})', flush=True)

print()
print(f'=== RESUMEN: {len(resueltos)} resueltos / {len(resueltos)+len(no_resueltos)} totales ===')
