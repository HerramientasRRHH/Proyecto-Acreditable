import sys
sys.path.insert(0, r'.claude\skills\acreditable-review\scripts')
from audit_antofagasta import cargar_lh, match_nombre_nomina_con_motivo

rows = cargar_lh(r'Documentos Antofagasta\2026-08-17 Libro de haberes Revisión Nuevo 2026-07-01.xlsx')
print(f'nomina completa: {len(rows)}')

# Casos "sin match" reportados por el usuario en la corrida real (IA leyó un nombre,
# el matcher lo rechazo)
sin_match = [
 "N.NEUFRAU","Zuleika Edith Angelica Soto Jara","Díaz","XIMENA BURGOS","Bonoso","Blanco",
 "Gahona Marco","URGEL NAVIEL","ASPRILLA CORDEROES CANDELARIO","Ivalios Roberto","Juan",
 "LIDIA GALARCE GALARCE","FLORES RICARDO","ABDODCO ALEXANDER","Jenny Duran Duncan",
 "Valaskka Tacnha","Cangana Fanny","FLORES / PATRICIA","Julio Ivan Julio Julio Javier Julio",
 "Olivia Jara","Juan Fernando","JEROME WASHINGTON","Cirujuhnia Nilicman","Elvira",
 "Jose Juvenal Colillier","Goñain","Silvia Pereira","Contreras","Barrera","Gonzalez Maria",
 "GONZALEZ CORVALAN","Julissa Aracely Abello","Contas","Eulain Contreras Galarce",
 "BONILLA CACERES MAURICIO","Gutmar Gomes","Bladimiro Jofré","Mary","Julio",
 "Renecillo Minham","IGNACIOS BRAVAN","VACARO ERAS","Yeltsi Cuero","Ramos Quezada Luz",
 "Alvarín","maitool","JHONNY QUISPE","JUAN YANES","Paula Realfa","JULIO MARTINEZ",
 "Guillermo","RASCO HURTADO JULIO","VACCAUS","Victor Nahuelan Diaz","HURCO","Rivera",
 "J. Urrutia","Olivera Avendaño Orlando","VICTOR","Sasha Mostert","Rolfes Rohr Adriana Keller",
 "Wilma","Rojas","SILVA MARIN E.H.","Tegue Santiago","Pascia Rojas","Alvarín",
 "ROJAS FRANCISCO","Flores","MUNOZ VELIZ VUC0","IBARGÜEN ILJA","VALENCIA ACOSTA LADIS",
 "Edwin Navarreo","Vasquez","Nalda","RUIZ ROBERTO","NOLAN ALEXIS NIEDERBUHL PEREZ FABIAN",
 "Herma Amelia","MONTERO ARACENA MIGUEL","Venusso Vejar","Núñez","Solano","Veliz",
 "Venanio O.","Silvia Juliet","Héctor Bañados Camaño","VIOLETA ANGEL","VILCA TAPIE JUAN",
 "Alibor","ORTEGA TAPIA","Antonio","Valeria Obenna","Lucumi Sulamit","Lucumi",
]

conteo = {'sin_tokens':0,'sin_candidatos':0,'sin_cobertura':0,'ambiguo':0,'ok':0}
ok_casos = []
ambiguos = []
for nombre in sin_match:
    match, motivo, candidatos = match_nombre_nomina_con_motivo(nombre, rows)
    conteo[motivo] += 1
    if motivo == 'ok':
        ok_casos.append((nombre, match['nombre']))
    if motivo == 'ambiguo':
        ambiguos.append((nombre, candidatos))

print('Distribución de motivos (réplica Python, misma nómina completa que usa hoy la app):')
for k,v in conteo.items():
    print(f'  {k}: {v}')

if ok_casos:
    print('\nCasos donde Python SI encuentra match (pero la app real dijo "sin match" -- posible bug real):')
    for n,m in ok_casos:
        print(f'  "{n}" -> {m}')

if ambiguos:
    print(f'\nCasos ambiguos ({len(ambiguos)}):')
    for n,c in ambiguos[:15]:
        print(f'  "{n}" -> empata entre: {c}')
