// La misma definición genera las preguntas y el resumen para no omitir respuestas.
// Formato de cada campo: [name, label, type, placeholder|opciones, requerido]
export const INTAKE_GROUPS = [
  { title: "01 · Conocer la oferta del hotel", help: "¿Quién evalúa las solicitudes y qué eventos puede atender el hotel?", fields: [
    ["responsable", "Encargada o encargado de eventos", "text", "Nombre y apellido", true],
    ["perfil", "Nombre de esta ficha", "text", "Ej. Oferta de eventos del hotel", true],
    ["cargo", "Cargo o área", "text", "Ej. Coordinación de eventos"],
    ["tipos_evento", "Tipos de eventos que pueden recibir", "textarea", "Seminarios, capacitaciones, congresos, reuniones…"],
    ["eventos_excluidos", "¿Qué solicitudes no atienden?", "textarea", "Eventos o condiciones fuera de la oferta del hotel."],
  ] },
  { title: "02 · Salones, asistentes y montaje", help: "Complete un salón y montaje de referencia. La capacidad puede cambiar según la distribución.", fields: [
    ["salon", "Salón o espacio de referencia", "text", "Nombre del salón"],
    ["montaje", "Montaje disponible", "select", ["Auditorio", "Escuela", "U", "Banquete", "Cóctel", "Directorio", "Otro"]],
    ["capacidad_min", "Capacidad mínima operativa (personas)", "number", "Si aplica"],
    ["capacidad_max", "Capacidad máxima para este montaje (personas)", "number", "Por confirmar con el hotel"],
    ["caracteristicas", "Características del salón", "textarea", "Superficie, accesibilidad, luz natural, climatización, acústica, divisiones…"],
    ["otros_salones", "Otros salones, montajes y capacidades", "textarea", "Salón / montaje / capacidad. Indique combinaciones posibles y restricciones."],
  ] },
  { title: "03 · Equipamiento y servicios adicionales", help: "Marque lo que el hotel puede ofrecer. Lo que no marque queda pendiente de confirmar.", fields: [
    ["equipamiento", "Equipamiento disponible", "checks", ["Proyector y pantalla", "Audio y micrófonos", "Internet / Wi-Fi", "Videoconferencia", "Iluminación", "Mobiliario"]],
    ["servicios", "Servicios adicionales", "checks", ["Alojamiento", "Coffee break", "Almuerzo o cena", "Banquetería", "Estacionamiento", "Apoyo técnico"]],
    ["condiciones_servicios", "Cantidades, costos y condiciones", "textarea", "¿Qué está incluido? ¿Qué depende de terceros? Indique cantidades y necesidades alimentarias que pueden atender."],
    ["otros_servicios", "Otros equipos o servicios", "textarea", "Streaming, traducción, transporte u otros."],
  ] },
  { title: "04 · Fechas, horarios y disponibilidad", help: "Defina cómo se confirma la agenda del hotel. No se presupone disponibilidad.", fields: [
    ["modulos", "Módulos que ofrece el hotel", "text", "Ej. mañana, tarde, jornada completa"],
    ["duracion_modulo", "Duración habitual por módulo", "text", "Ej. media jornada: 4 horas"],
    ["fuente_agenda", "Fuente para consultar disponibilidad", "select", ["Calendario de eventos del hotel", "Sistema de reservas", "Planilla de disponibilidad", "Consulta directa al equipo", "Otro"]],
    ["validador_agenda", "¿Quién confirma la disponibilidad?", "text", "Cargo o persona responsable"],
    ["anticipacion", "Anticipación mínima (días)", "number", "Ej. 7"],
    ["montaje_tiempo", "Tiempo de montaje y desmontaje", "text", "Ej. 1 hora antes y 1 hora después"],
    ["restricciones_agenda", "Fechas bloqueadas y restricciones horarias", "textarea", "Días no disponibles, eventos simultáneos, horarios límite, temporadas…"],
  ] },
  { title: "05 · Solicitud de referencia (opcional)", help: "Use un evento de ejemplo para precisar qué información se necesita. No representa una reserva confirmada.", fields: [
    ["evento_solicitado", "Tipo de evento solicitado", "text", "Ej. Seminario"],
    ["asistentes", "Cantidad de asistentes solicitada", "number", "Ej. 80"],
    ["fecha_evento", "Fecha de inicio del evento", "date"], ["fecha_fin", "Fecha de término del evento", "date"],
    ["hora_inicio", "Hora de inicio", "time"], ["hora_fin", "Hora de término", "time"],
    ["duracion", "Duración total solicitada (horas)", "number", "Ej. 8"],
    ["modulo_solicitado", "Horario o módulo solicitado", "text", "Ej. jornada completa"],
    ["requisitos_solicitados", "Salón, equipos y servicios requeridos", "textarea", "Detalle lo solicitado y sus cantidades para compararlo con la oferta del hotel."],
  ] },
  { title: "06 · Criterios que importan al evaluar", help: "Indique qué es obligatorio, qué se puede negociar y qué no influye en la decisión. Sin respuestas predeterminadas.", matrix: true, fields: [
    ["descarte", "¿Qué condición obliga a descartar una solicitud?", "textarea", "Ej. No disponer del salón en la fecha solicitada."],
    ["negociable", "¿Qué se puede adaptar o negociar?", "textarea", "Montaje, menú, fecha, equipamiento…"],
    ["faltantes", "¿Qué hacer si falta información?", "select", ["Solicitar aclaración y dejar pendiente", "Revisar manualmente con el equipo", "Descartar solo si falta un requisito obligatorio"]],
  ] },
  { title: "07 · Condiciones comerciales y validación", help: "Registre otras restricciones que influyen en la decisión comercial.", fields: [
    ["minimo", "Presupuesto mínimo aceptable (CLP)", "number", "Si aplica"],
    ["maximo", "Presupuesto máximo de referencia (CLP)", "number", "Si aplica"],
    ["notas", "Otras condiciones relevantes", "textarea", "Forma de pago, documentación, cancelaciones, ubicación o requisitos especiales."],
    ["validador_final", "¿Quién valida la decisión final?", "text", "Cargo o persona"],
    ["estado_ficha", "Estado del perfil", "select", ["Borrador por validar con el cliente", "Revisado con la encargada de eventos"]],
  ] },
  { title: "08 · Palabras y frases de interés", help: "Escriba sus términos a mano o incorpore sugerencias revisadas. Separe cada palabra o frase con un salto de línea. Estos criterios orientarían el filtrado y la interpretación del futuro LLM.", interests: true, fields: [
    ["intereses_palabras", "Palabras de interés y sinónimos", "textarea", "Ej. alojamiento\nhospedaje\nseminario"],
    ["intereses_frases", "Frases que describen oportunidades de interés", "textarea", "Ej. Organización de seminarios con coffee break"],
    ["exclusiones_busqueda", "Palabras o frases que desea excluir", "textarea", "Solo exclusiones confirmadas por el equipo. Ej. venta de mobiliario"],
  ] },
];

export const IMPORTANCE = [["tipo", "Tipo de evento"], ["asistentes", "Cantidad de asistentes"], ["salon", "Características y montaje del salón"], ["equipos", "Equipamiento necesario"], ["fecha", "Fecha y disponibilidad"], ["horario", "Horario o módulo"], ["duracion", "Duración"], ["servicios", "Servicios adicionales"], ["presupuesto", "Presupuesto"]];
