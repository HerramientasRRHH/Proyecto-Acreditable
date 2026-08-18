import sys, re
sys.path.insert(0, r'C:\Users\agutierrez\Desktop\Proyectos\Proyecto Acreditable\.claude\skills\acreditable-review\scripts')
from audit_antofagasta import get_pdf_text_ocr, find_all_ruts, norm_rut
import os

base = r'C:\Users\agutierrez\Desktop\Proyectos\Proyecto Acreditable\Documentos Antofagasta\H).-Finiquitos - Seguro Cesantia - Contratos - Liquidaciones\liquidaciones'

casos_por_archivo = {
    'A. liquidación letra A.pdf': [('13.603.630-0','Astete Gutierrez Alex Marco'),('25.435.250-0','Arrechea Riascos Dora'),('6.305.214-0','Araya Araya Victor Hugo'),('25.793.500-0','Arboleda Agualimpia Sandra Patricia'),('8.559.961-5','Araya Barraza David Antonio')],
    'C. liquidaciones letra C.pdf': [('23.162.740-5','Correa Castañeda Nila'),('25.797.456-1','Cuero Asprilla Maria Enith')],
    'D. liquidaciones letra D.pdf': [('26.426.053-1','Duran Ragua Jose Javier'),('13.191.732-5','De La Cruz Pacheco Hector Pascual Eugenio')],
    'E. liquidaciones letra E y F.pdf': [('5.859.211-0','Fredes Jeraldo Ana Maria')],
    'G. liquidaciones letra G.pdf': [('20.543.463-1','Gahona Zaragoza Marco Nicanor'),('13.357.030-6','Gutierrez Araya Evelyn Marcela'),('21.735.599-0','Gahona Zaragoza Mauricio Nicolas'),('12.610.974-1','Guzman Morales Teresa Isolina'),('13.867.833-4','Gallardo Pinto Jessica Diana')],
    'M. liquidaciones letra M.pdf': [('25.600.854-8','Muñoz Velez Yuced Alexis'),('28.982.236-4','Medina Paredes Marcos'),('10.894.899-k','Morales Vargas Domingo Segundo'),('12.613.084-8','Marin Miranda Jose Manuel'),('24.608.704-0','Mosquera Quiñones Kelly Xilena')],
    'O. liquidaciones letra O.pdf': [('29.131.524-0','Ovando Subia Juan Luis')],
    'P. Liquidaciones letra P.pdf': [('13.649.071-0','Pizarro Alvarez Cristian Alamiro'),('25.758.455-0','Polo Chavez Maribel'),('12.214.513-1','Parra Pasten Patricia'),('8.492.785-6','Pinto Lang Jimena Del Carmen'),('16.704.924-9','Poveda Antiguay Pedro Alizander'),('28.682.481-1','Pacosillo  Mirian Jeanette')],
    'R. liquidaciones leta R.pdf': [('25.530.716-9','Riascos Hurtado Julio Alberto'),('28.980.298-3','Rivera Angelo Eusebia'),('24.442.380-9','Rojas Zarate Noemi Abigail'),('24.292.008-2','Romero Mosquera Lludi Amparo')],
    'S. liquidaciones letra S.pdf': [('27.855.596-8','Salazar Mondragon Carlos Alberto'),('24.059.843-4','Seballo Moscoso Filandia Carmen'),('6.422.552-9','Salinas Menchaca Rafael Luis'),('28.632.937-3','Segovia Laura Maily'),('10.652.096-8','Segovia Salazar Andres'),('25.713.010-k','Sevillano Zelada Serafina')],
    'T. liquidaciones letra T.pdf': [('16.203.451-0','Toro Inostroza Alejandro Ignacio'),('21.188.462-2','Torrealba Rivadera Dayana Andrea'),('17.939.062-0','Tapia Colome Margarita Haydee')],
    'liquidaciones letra L.pdf': [('25.855.827-8','Landazuri Cuero Mary Santos')],
}

resumen = {'encontrados_rut': [], 'encontrados_solo_apellido': [], 'genuinamente_ausentes': []}

for archivo, casos in casos_por_archivo.items():
    path = os.path.join(base, archivo)
    print(f'=== procesando {archivo} ===', flush=True)
    txt, total = get_pdf_text_ocr(path, max_pages_ocr=100, verbose=True)
    ruts_doc = find_all_ruts(txt)
    txt_upper = txt.upper()
    for rut, nombre in casos:
        rn = norm_rut(rut)
        apellido = nombre.split()[0].upper()
        en_ruts = rn in ruts_doc
        en_texto_apellido = apellido in txt_upper
        if en_ruts:
            resumen['encontrados_rut'].append((rut, nombre, archivo))
            print(f'  ENCONTRADO POR RUT: {nombre} ({rut})', flush=True)
        elif en_texto_apellido:
            resumen['encontrados_solo_apellido'].append((rut, nombre, archivo))
            print(f'  APELLIDO EN TEXTO PERO RUT NO MATCHEA: {nombre} ({rut})', flush=True)
        else:
            resumen['genuinamente_ausentes'].append((rut, nombre, archivo))
            print(f'  NO ENCONTRADO (ni RUT ni apellido): {nombre} ({rut})', flush=True)

print()
print('=== RESUMEN FINAL ===')
print(f'Encontrados por RUT (bug real de cruce, el RUT SI esta en el doc): {len(resumen["encontrados_rut"])}')
print(f'Apellido en texto pero RUT no matchea (posible RUT mal leido): {len(resumen["encontrados_solo_apellido"])}')
print(f'Genuinamente ausentes (ni RUT ni apellido en el texto): {len(resumen["genuinamente_ausentes"])}')
