# edifier-r990bt-control

Control del parlante **Edifier R990BT** desde la computadora por Bluetooth LE, sin usar la perilla trasera ni el celular: cambio de entrada (Bluetooth, Line 1, Line 2) y, si el parlante lo admite, volumen y ecualizador.

> Proyecto no oficial, sin relación con Edifier. Usa un protocolo no documentado, descifrado por la comunidad a partir de la app EDIFIER ConneX. Usalo bajo tu responsabilidad.

## Estado

| Fase | Objetivo | Estado |
|---|---|---|
| 1 | Conectar, leer estado y obtener los códigos de entrada | hecho |
| 2 | App con ventana e ícono en la bandeja de Windows | en prueba |
| 3 | Instalador o `.exe` para no depender de Python | pendiente |

Valores confirmados en un R990BT con firmware 1.0.2:

| Función | Consulta | Cambio | Valores |
|---|---|---|---|
| Entrada | `AA EC 61 00 00 F7` | `AA EC 62 00 02 06 <entrada> <chk>` | `01` Bluetooth, `02` Line 1, `03` Line 2 |
| Volumen | `AA EC 66 00 00 FC` | `AA EC 67 00 01 <vol> <chk>` | 0 a 16 |
| Ecualizador | `AA EC D5 00 00 6B` | `AA EC C4 00 01 <preset> <chk>` | `00`, `01`, `02` (nombres sin confirmar) |

Para el cambio de entrada, el formato está deducido del M60 y del M90; en el R990BT solo se verificó la consulta.

## Usar la app

Después de la instalación (ver más abajo), hacé doble clic en **`Edifier R990BT.pyw`**. Se abre una ventana con:

- **Entrada:** Bluetooth, Line 1 y Line 2.
- **Volumen:** control deslizante y botones `-` / `+`.
- **Ecualizador:** los tres presets del parlante.

Al cerrar la ventana, la app sigue en la bandeja del sistema, junto al reloj. Desde el menú del ícono se puede cambiar la entrada sin abrir la ventana. Para salir del todo, elegí **Salir** en ese menú.

La primera vez la app busca el parlante y guarda su dirección en `%APPDATA%\edifier-r990bt-control\config.json`. Si cambiás de parlante, borrá ese archivo.

Si doble clic no abre nada, corré esto en una consola en la carpeta del proyecto para ver el error:

```bash
py -m edifier_ctl.gui
```

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

## Herramienta de diagnóstico

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

La primera vez que encuentra el parlante, el programa guarda su dirección y después la usa directamente, porque el parlante se anuncia por BLE solo de a ratos. Para usar otro parlante, corré `py -m edifier_ctl forget`, o agregá `--address XX:XX:XX:XX:XX:XX` a cualquier comando.

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
