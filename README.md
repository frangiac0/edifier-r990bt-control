# edifier-r990bt-control

Control del parlante **Edifier R990BT** desde la computadora por Bluetooth LE, sin usar la perilla trasera ni el celular: cambio de entrada (Bluetooth, Line 1, Line 2) y, si el parlante lo admite, volumen y ecualizador.

> Proyecto no oficial, sin relación con Edifier. Usa un protocolo no documentado, descifrado por la comunidad a partir de la app EDIFIER ConneX. Usalo bajo tu responsabilidad.

## Estado

**Fase 1: diagnóstico.** Todavía no hay interfaz gráfica. Esta versión trae una herramienta de línea de comandos para confirmar que el R990BT usa el mismo protocolo que otros modelos Edifier compatibles con ConneX y para averiguar sus códigos de entrada.

| Fase | Objetivo | Estado |
|---|---|---|
| 1 | Conectar, leer estado y obtener los códigos de entrada | en curso |
| 2 | Captura del tráfico de ConneX, solo si la fase 1 no alcanza | pendiente |
| 3 | App de bandeja para Windows con selector de entrada | pendiente |

## Cómo funciona

El parlante tiene dos canales Bluetooth independientes:

- **Bluetooth clásico (A2DP):** transporta el audio.
- **Bluetooth LE:** recibe los comandos de control que usa la app ConneX.

Este programa usa solamente el segundo. En otros modelos de la familia (M60, M90, MR5BT), el control funciona con tramas como estas:

```text
AA EC <opcode> <largo:2 bytes> <datos> <checksum>    pedido
BB EC <opcode> <largo:2 bytes> <datos> <checksum>    respuesta
```

La consulta `0x61` devuelve `<grupo> <entrada>` y el comando `0x62` cambia la entrada. El grupo y los códigos de entrada cambian según el modelo, así que hay que leerlos del propio R990BT.

## Requisitos

- Windows 10 u 11 con Bluetooth 4.0 o superior. Casi todas las notebooks lo tienen; en una PC de escritorio puede hacer falta un adaptador USB.
- Python 3.10 o superior.

## Instalación en Windows

1. Instalá Python desde [python.org](https://www.python.org/downloads/). En el instalador, tildá **"Add python.exe to PATH"**.
2. Descargá este repositorio con el botón verde **Code > Download ZIP** y descomprimilo.
3. Abrí la carpeta descomprimida, hacé clic en la barra de direcciones del Explorador, escribí `cmd` y apretá Enter. Se abre una consola en esa carpeta.
4. Instalá la dependencia:

```bash
py -m pip install -r requirements.txt
```

## Diagnóstico paso a paso

Antes de empezar:

- **Cerrá la app ConneX en el celular**, o apagá el Bluetooth del celular. El parlante acepta un solo cliente de control a la vez.
- En otros modelos, el parlante solo se anuncia por BLE mientras recibe audio por Bluetooth. Si no aparece, poné música desde la PC o desde el celular y volvé a intentar.

### 1. Buscar el parlante

```bash
py -m edifier_ctl scan
```

Si no aparece nada, listá todos los dispositivos BLE cercanos:

```bash
py -m edifier_ctl scan --all
```

### 2. Ver qué expone

```bash
py -m edifier_ctl gatt
```

Lo que importa es si aparece un servicio con la forma `4809xxxx-1a48-11e9-ab14-d663bd873d93`.

### 3. Leer el estado

```bash
py -m edifier_ctl info
```

### 4. Descubrir los códigos de entrada

```bash
py -m edifier_ctl watch
```

Con esto corriendo, girá o apretá la perilla del parlante para pasar por Bluetooth, Line 1 y Line 2. Esperá unos segundos en cada una y anotá qué código aparece para cada entrada. Terminá con `Ctrl+C`.

### 5. Probar el cambio de entrada

Con el grupo y el código que mostró `watch` (en hexadecimal):

```bash
py -m edifier_ctl source <grupo> <entrada>
```

Ejemplo, si el grupo es `0F` y Line 1 es `02`:

```bash
py -m edifier_ctl source 0F 02
```

Si encontraste varios parlantes, agregá `--address XX:XX:XX:XX:XX:XX` a cualquier comando.

### Resultado

Todo lo que muestra la herramienta se guarda también en `diagnostico.txt`, en la misma carpeta. Ese archivo es el que sirve para avanzar a la fase siguiente. Si lo vas a publicar, antes borrá las direcciones Bluetooth.

## Si el diagnóstico no alcanza

Si el parlante no responde a estas consultas, hay que capturar lo que manda ConneX desde un Android. Ver [docs/CAPTURA_ANDROID.md](docs/CAPTURA_ANDROID.md).

## Referencias

Proyectos comunitarios que documentaron el protocolo en otros modelos:

- [kralonur/edifier-speakers-ble](https://github.com/kralonur/edifier-speakers-ble): M60 y M90, incluido el cambio de entrada.
- [hifn123p/edifier-center](https://github.com/hifn123p/edifier-center): MR5BT, app de bandeja para Windows.
- [Devis99/omarchy-edifier-mr5](https://github.com/Devis99/omarchy-edifier-mr5): MR5.

## Licencia

MIT
