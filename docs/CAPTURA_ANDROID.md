# Capturar los comandos de ConneX en Android

Hace falta solo si el diagnóstico de la fase 1 no logra leer o cambiar la entrada. La idea es grabar los paquetes Bluetooth que manda la app oficial cuando cambiás de entrada, para copiar los comandos exactos.

## 1. Activar las opciones de desarrollador

1. Entrá a **Ajustes > Acerca del teléfono**. En algunos teléfonos está en **Información de software**.
2. Tocá siete veces **Número de compilación** hasta que aparezca el aviso de que ya sos desarrollador.

## 2. Activar el registro Bluetooth

1. Entrá a **Ajustes > Sistema > Opciones de desarrollador**.
2. Activá **Habilitar registro de Bluetooth HCI** (en inglés, *Enable Bluetooth HCI snoop log*). Si te da opciones, elegí **Habilitado** o **Completo**.
3. Apagá y prendé el Bluetooth del celular para que el registro empiece de cero.

## 3. Grabar las acciones

1. Abrí EDIFIER ConneX y conectate al R990BT.
2. Hacé estas acciones despacio, dejando unos 5 segundos entre cada una, y anotá la hora:
   - pasar a **Line 1**
   - pasar a **Line 2**
   - volver a **Bluetooth**
   - subir el volumen un paso y bajarlo un paso, si la app lo permite
   - cambiar a cada ecualizador predefinido
3. Cerrá la app.

## 4. Sacar el registro

1. En **Opciones de desarrollador**, tocá **Generar informe de errores** y elegí **Informe interactivo**.
2. Cuando termine, va a llegar una notificación. Compartí el `.zip` a tu computadora por Drive, mail o cable USB.
3. Dentro del zip, el registro está en `FS/data/misc/bluetooth/logs/btsnoop_hci.log` o en una ruta parecida.
4. Desactivá **Habilitar registro de Bluetooth HCI**.

## Privacidad

El informe de errores completo trae mucha información personal del teléfono. **No subas el `.zip` a GitHub ni lo compartas.** Sacá solamente `btsnoop_hci.log`. Ese archivo también incluye direcciones Bluetooth de tus dispositivos, así que tampoco lo publiques tal cual.

## Qué se busca en el registro

Hay que buscar las escrituras a la característica `48090002-...` y las notificaciones de `48090001-...`. Se pueden ver con Wireshark usando el filtro `btatt`. Las tramas que empiezan con `AA EC 62` corresponden al cambio de entrada.
