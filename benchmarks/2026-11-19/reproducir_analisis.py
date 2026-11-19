#!/usr/bin/env python3
"""Regenera los cinco gráficos y verifica métricas desde los CSV anonimizados.

Dependencias: Python 3, matplotlib. Sin red, cámaras, Home Assistant ni Docker.
"""
from pathlib import Path
import csv
import statistics as st
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

BASE = Path(__file__).resolve().parent
DATA = BASE / 'datos'
FIGS = BASE / 'figuras'
FIGS.mkdir(exist_ok=True)
COLORS = {1: '#7594b8', 4: '#33748b', 8: '#d57443'}
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.titlesize': 12,
    'axes.spines.top': False, 'axes.spines.right': False,
    'savefig.dpi': 190, 'axes.labelcolor': '#334155',
    'text.color': '#1e293b', 'axes.titleweight': 'semibold',
})

def rows(name):
    with (DATA / name).open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))

def save(name):
    plt.tight_layout(pad=1.9)
    plt.savefig(FIGS / name, bbox_inches='tight', facecolor='white')
    plt.close()

S = {n: [r for r in rows(f'samples_{n:02d}.csv') if r['phase']=='sostenido'] for n in (1,4,8)}
C = {n: rows(f'cameras_{n:02d}.csv') for n in (1,4,8)}
SUM = rows('summary.csv')

for n in (1, 4, 8):
    cpu = [float(r['cpu_docker_pct']) for r in S[n]]
    mem = [float(r['mem_mib']) for r in S[n]]
    ts = [float(r['first_ts_s']) for r in C[n]]
    row = next(r for r in SUM if int(r['concurrency']) == n)
    assert len(cpu) == int(row['samples_steady']) == 30
    assert abs(st.mean(cpu)-float(row['cpu_avg_pct'])) < 0.01
    assert max(cpu) == float(row['cpu_peak_pct'])
    assert max(mem) == float(row['memory_peak_mib'])
    assert sum(int(r['unique_segments']) for r in C[n]) == int(row['total_unique_segments'])
    assert all(int(r['http_errors'])==0 and int(r['other_errors'])==0 for r in C[n])
    print(f'{n} canales: CPU {st.mean(cpu):.2f}% (pico {max(cpu):.2f}%), '
          f'RAM {max(mem):.1f} MiB, primer TS media {st.mean(ts):.3f} s, '
          f'brechas >5 s {sum(float(r["max_gap_new_ts_s"])>5 for r in C[n])}')

plt.figure(figsize=(9.5,4.6))
for n in (1,4,8):
    r=S[n]; start=float(r[0]['elapsed_s'])
    plt.plot([float(x['elapsed_s'])-start for x in r], [float(x['cpu_docker_pct']) for x in r],
             label=f'{n} cámara'+('s' if n>1 else ''),color=COLORS[n],lw=2,marker='o',markersize=2.6)
plt.xlabel('Tiempo desde inicio de ventana sostenida (s)');plt.ylabel('CPU Docker (%)')
plt.title('Uso de CPU durante 60 s de transmisión sostenida');plt.ylim(0,270);plt.xlim(0,61)
plt.legend(loc='upper left',frameon=False);plt.grid(axis='y',alpha=.15)
save('cpu_serie_temporal.png')

plt.figure(figsize=(9.5,4.6))
for n in (1,4,8):
    r=S[n]; start=float(r[0]['elapsed_s'])
    plt.plot([float(x['elapsed_s'])-start for x in r], [float(x['mem_mib']) for x in r],
             label=f'{n} cámara'+('s' if n>1 else ''),color=COLORS[n],lw=2,marker='o',markersize=2.6)
plt.xlabel('Tiempo desde inicio de ventana sostenida (s)');plt.ylabel('RAM contenedor (MiB)')
plt.title('Memoria durante 60 s de transmisión sostenida');plt.xlim(0,61)
plt.legend(loc='upper left',frameon=False);plt.grid(axis='y',alpha=.15)
save('memoria_serie_temporal.png')

labels=[r['camera_id'].replace('camera_','C') for r in C[8]]
startup=[float(r['first_ts_s']) for r in C[8]]
plt.figure(figsize=(9,4.3));plt.barh(labels,startup,color=COLORS[8],alpha=.9)
for y,v in enumerate(startup):plt.text(v+.2,y,f'{v:.2f} s',va='center',fontsize=9)
plt.gca().invert_yaxis();plt.xlabel('Primer segmento TS (s)');plt.xlim(0,20.5)
plt.title('Tiempo de arranque con ocho cámaras');plt.grid(axis='x',alpha=.13)
save('arranque_8_camaras.png')

gaps=[float(r['max_gap_new_ts_s']) for r in C[8]]
plt.figure(figsize=(9,4.3));plt.barh(labels,gaps,color=['#c06143' if v>5 else '#507c99' for v in gaps])
for y,v in enumerate(gaps):plt.text(v+.13,y,f'{v:.2f} s',va='center',fontsize=9)
plt.gca().invert_yaxis();plt.axvline(5,color='#b91c1c',ls='--',lw=1,label='Umbral de auditoría 5 s (no criterio Alexa)')
plt.xlabel('Mayor intervalo entre segmentos TS nuevos (s)');plt.title('Regularidad: ocho cámaras')
plt.xlim(0,13.6);plt.grid(axis='x',alpha=.13);plt.legend(loc='upper right',frameon=False,fontsize=8)
save('intervalos_maximos_8_camaras.png')

names=['1','4','8']; mean=[float(r['cpu_avg_pct']) for r in SUM]; peaks=[float(r['cpu_peak_pct']) for r in SUM]
plt.figure(figsize=(8.7,4.5)); x=[0,1,2]; w=.34
plt.bar([i-w/2 for i in x],mean,width=w,label='Media',color='#347b91')
plt.bar([i+w/2 for i in x],peaks,width=w,label='Pico',color='#cb7d4f')
for offset, vals in [(-w/2,mean),(w/2,peaks)]:
    for i,v in enumerate(vals):plt.text(i+offset,v+4,f'{v:.1f}%',ha='center',fontsize=9)
plt.xticks(x,names);plt.xlabel('Cámaras simultáneas');plt.ylabel('CPU Docker (%)')
plt.ylim(0,275);plt.title('CPU por concurrencia');plt.legend(frameon=False);plt.grid(axis='y',alpha=.15)
save('cpu_vs_concurrencia.png')
print(f'Gráficos regenerados en: {FIGS}')
