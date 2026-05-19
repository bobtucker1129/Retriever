"""Bilingual Help content for the Retriever rebuild."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from app.auth.permissions import CurrentUser

Text = dict[str, str]
HelpTopic = dict[str, Any]
HelpModule = dict[str, Any]


def _text(en: str, es: str) -> Text:
    return {"en": en, "es": es}


HELP_MODULES: list[HelpModule] = [
    {
        "slug": "getting-access-users",
        "nav_key": "admin",
        "title": _text("Getting Access / Users", "Acceso / Usuarios"),
        "summary": _text(
            "Sign in, understand pending access, and manage user records when you are an admin.",
            "Inicie sesión, entienda el acceso pendiente y administre usuarios si es administrador.",
        ),
        "kicker": _text("Accounts", "Cuentas"),
        "permission": "active",
        "topics": [
            {
                "slug": "request-access",
                "title": _text("Request access", "Pedir acceso"),
                "summary": _text(
                    "What to do when Retriever says your access is pending.",
                    "Qué hacer cuando Retriever dice que su acceso está pendiente.",
                ),
                "steps": [
                    _text("Sign in with your Boone email.", "Inicie sesión con su correo de Boone."),
                    _text(
                        "If you land on the pending page, ask a Retriever admin to activate your profile.",
                        "Si llega a la página pendiente, pida a un administrador que active su perfil.",
                    ),
                    _text(
                        "Tell the admin which areas you need: Fetch, Wiki, PrePress, DSF, or Inventory.",
                        "Diga al administrador qué áreas necesita: Fetch, Wiki, PrePress, DSF o Inventario.",
                    ),
                ],
                "notes": [
                    _text(
                        "Do not share someone else's account; access is tied to your own identity.",
                        "No use la cuenta de otra persona; el acceso está ligado a su identidad.",
                    )
                ],
            },
            {
                "slug": "manage-users",
                "title": _text("Manage users", "Administrar usuarios"),
                "summary": _text(
                    "Admin-only basics for activating users and assigning modules.",
                    "Conceptos básicos solo para administradores para activar usuarios y asignar módulos.",
                ),
                "admin_only": True,
                "steps": [
                    _text("Open Admin, then Users.", "Abra Admin y luego Usuarios."),
                    _text("Find the employee record and confirm the email is correct.", "Busque el usuario y confirme que el correo sea correcto."),
                    _text("Set status to active only for approved employees.", "Cambie el estado a activo solo para empleados aprobados."),
                    _text("Grant only the modules the person needs for their job.", "Conceda solo los módulos que la persona necesita para su trabajo."),
                ],
                "notes": [
                    _text(
                        "Normal users do not see admin-only setup details in Help.",
                        "Los usuarios normales no ven detalles de configuración solo para administradores.",
                    )
                ],
            },
        ],
    },
    {
        "slug": "fetch",
        "nav_key": "fetch",
        "title": _text("Fetch", "Fetch"),
        "summary": _text(
            "Ask operational questions, keep conversations organized, and download returned report files.",
            "Haga preguntas operativas, mantenga conversaciones organizadas y descargue reportes.",
        ),
        "kicker": _text("Assistant", "Asistente"),
        "permission": "fetch",
        "topics": [
            {
                "slug": "ask-a-question",
                "title": _text("Ask a question", "Hacer una pregunta"),
                "summary": _text(
                    "Use plain language first; Fetch handles routing behind the scenes.",
                    "Use lenguaje normal primero; Fetch decide la ruta en segundo plano.",
                ),
                "steps": [
                    _text("Open Fetch from the sidebar.", "Abra Fetch desde la barra lateral."),
                    _text("Start a new chat or reopen an existing one.", "Empiece un chat nuevo o abra uno existente."),
                    _text("Type the question with enough detail to identify the job, customer, or report range.", "Escriba la pregunta con suficiente detalle para identificar el trabajo, cliente o rango del reporte."),
                    _text("Open any source links or download buttons returned in the answer.", "Abra los enlaces de fuente o botones de descarga que aparezcan en la respuesta."),
                ],
                "notes": [
                    _text(
                        "Use a narrower follow-up if an answer is too broad.",
                        "Use una pregunta más específica si la respuesta es demasiado amplia.",
                    )
                ],
            },
            {
                "slug": "reports-and-files",
                "title": _text("Reports and files", "Reportes y archivos"),
                "summary": _text(
                    "How to handle exports, delayed files, and upload-grounded questions.",
                    "Cómo manejar exportaciones, archivos demorados y preguntas con adjuntos.",
                ),
                "steps": [
                    _text("Ask for CSV, Excel, PDF, or a chart when you need a reusable report.", "Pida CSV, Excel, PDF o una gráfica cuando necesite un reporte reutilizable."),
                    _text("If a file is still building, use the thread refresh panel before asking again.", "Si el archivo todavía se está creando, use el panel de actualizar antes de preguntar otra vez."),
                    _text("Attach files directly in Fetch when the answer must use uploaded content.", "Adjunte archivos en Fetch cuando la respuesta debe usar ese contenido."),
                ],
            },
        ],
    },
    {
        "slug": "wiki",
        "nav_key": "wiki",
        "title": _text("Wiki", "Wiki"),
        "summary": _text(
            "Find Boone procedures, work instructions, ISO references, and internal knowledge cards.",
            "Encuentre procedimientos, instrucciones de trabajo, referencias ISO y tarjetas internas.",
        ),
        "kicker": _text("Knowledge", "Conocimiento"),
        "permission": "wiki",
        "topics": [
            {
                "slug": "find-documents",
                "title": _text("Find documents", "Buscar documentos"),
                "summary": _text(
                    "Use category cards and document cards to stay inside Retriever.",
                    "Use categorías y tarjetas para mantenerse dentro de Retriever.",
                ),
                "steps": [
                    _text("Open Wiki from the sidebar.", "Abra Wiki desde la barra lateral."),
                    _text("Use SweetProcess links for existing daily procedures.", "Use enlaces de SweetProcess para procedimientos diarios existentes."),
                    _text("Open work instruction cards for controlled Retriever summaries.", "Abra tarjetas de instrucciones de trabajo para resúmenes controlados."),
                ],
            },
            {
                "slug": "source-status",
                "title": _text("Source status", "Estado de fuentes"),
                "summary": _text(
                    "Understand synced source freshness while the wiki intake layer grows.",
                    "Entienda la frescura de fuentes sincronizadas mientras crece la wiki.",
                ),
                "steps": [
                    _text("Check the Sync status panel on Wiki.", "Revise el panel Estado de sincronización en Wiki."),
                    _text("Use draft cards cautiously until summaries are reviewed.", "Use tarjetas borrador con cuidado hasta que los resúmenes sean revisados."),
                ],
            },
        ],
    },
    {
        "slug": "prepress",
        "nav_key": "prepress",
        "title": _text("PrePress", "PrePress"),
        "summary": _text(
            "Work the WIP queue, filter jobs, track proof rounds, and open job tickets.",
            "Trabaje la cola WIP, filtre trabajos, siga pruebas y abra tickets de trabajo.",
        ),
        "kicker": _text("Production", "Producción"),
        "permission": "prepress",
        "topics": [
            {
                "slug": "work-the-queue",
                "title": _text("Work the queue", "Trabajar la cola"),
                "summary": _text(
                    "Keep WIP focused with filters, sort controls, and current job state.",
                    "Mantenga WIP enfocado con filtros, orden y estado actual del trabajo.",
                ),
                "steps": [
                    _text("Open PrePress and choose the queue or filter you need.", "Abra PrePress y elija la cola o filtro que necesita."),
                    _text("Sort by invoice, assigned operator, proof date, or hold status.", "Ordene por factura, operador asignado, fecha de prueba o estado de espera."),
                    _text("Use completed reference mode only when checking recent completed work.", "Use el modo de completados solo para revisar trabajo terminado reciente."),
                ],
            },
            {
                "slug": "job-tickets",
                "title": _text("Job tickets", "Tickets de trabajo"),
                "summary": _text(
                    "Open PrintSmith tickets from Retriever when your account and network allow it.",
                    "Abra tickets de PrintSmith desde Retriever cuando su cuenta y red lo permitan.",
                ),
                "steps": [
                    _text("Load the invoice or job part row.", "Cargue la fila de factura o parte de trabajo."),
                    _text("Use the ticket link to open PrintSmith in a new tab.", "Use el enlace de ticket para abrir PrintSmith en una pestaña nueva."),
                    _text("If it fails, confirm PrintSmith access before retrying.", "Si falla, confirme el acceso a PrintSmith antes de reintentar."),
                ],
            },
        ],
    },
    {
        "slug": "dsf",
        "nav_key": "dsf",
        "title": _text("DSF", "DSF"),
        "summary": _text(
            "Look up DSF invoices and run common cleanup actions before production.",
            "Busque facturas DSF y ejecute acciones comunes antes de producción.",
        ),
        "kicker": _text("Orders", "Órdenes"),
        "permission": "dsf",
        "topics": [
            {
                "slug": "invoice-lookup",
                "title": _text("Invoice lookup", "Buscar factura"),
                "summary": _text(
                    "Load a DSF invoice before choosing actions.",
                    "Cargue una factura DSF antes de elegir acciones.",
                ),
                "steps": [
                    _text("Open DSF from the sidebar.", "Abra DSF desde la barra lateral."),
                    _text("Enter the invoice number and run lookup.", "Escriba el número de factura y ejecute la búsqueda."),
                    _text("Review the customer, title, shipping, and job part details.", "Revise cliente, título, envío y detalles de partes del trabajo."),
                ],
            },
            {
                "slug": "common-actions",
                "title": _text("Common actions", "Acciones comunes"),
                "summary": _text(
                    "Apply only the changes needed for the loaded order.",
                    "Aplique solo los cambios necesarios para la orden cargada.",
                ),
                "steps": [
                    _text("Assign the correct project manager when needed.", "Asigne el gerente de proyecto correcto cuando sea necesario."),
                    _text("Update proofreader, shipping, wanted date, title, or handling fee fields deliberately.", "Actualice revisor, envío, fecha requerida, título o manejo con cuidado."),
                    _text("Reload the invoice after an action if the screen does not update.", "Recargue la factura después de una acción si la pantalla no se actualiza."),
                ],
            },
        ],
    },
    {
        "slug": "inventory",
        "nav_key": "inventory",
        "title": _text("Inventory", "Inventario"),
        "summary": _text(
            "Scan stock in or out, review products and customers, print shelf tags, and run counts.",
            "Escanee entradas o salidas, revise productos y clientes, imprima etiquetas y haga conteos.",
        ),
        "kicker": _text("Warehouse", "Bodega"),
        "permission": "inventory",
        "topics": [
            {
                "slug": "scan-pull",
                "title": _text("Scan and pull", "Escanear y retirar"),
                "summary": _text(
                    "Remove stock when fulfilling an order.",
                    "Retire inventario al cumplir una orden.",
                ),
                "steps": [
                    _text("Open Inventory, then Scan.", "Abra Inventario y luego Escanear."),
                    _text("Choose Pull and scan or enter the product barcode.", "Elija Retirar y escanee o escriba el código del producto."),
                    _text("Enter quantity and confirm the customer or order note.", "Escriba cantidad y confirme cliente o nota de orden."),
                    _text("Submit once; warnings appear for unusually large pulls.", "Envíe una vez; aparecerán avisos para retiros inusuales."),
                ],
            },
            {
                "slug": "scan-add",
                "title": _text("Scan and add", "Escanear y agregar"),
                "summary": _text(
                    "Receive new stock into a product location.",
                    "Reciba inventario nuevo en una ubicación de producto.",
                ),
                "steps": [
                    _text("Choose Add on the scan screen.", "Elija Agregar en la pantalla de escaneo."),
                    _text("Scan or enter the barcode and confirm the product.", "Escanee o escriba el código y confirme el producto."),
                    _text("Enter the received quantity and save the transaction.", "Escriba la cantidad recibida y guarde la transacción."),
                ],
            },
            {
                "slug": "products-customers",
                "title": _text("Products and customers", "Productos y clientes"),
                "summary": _text(
                    "Browse, edit, retire, and group stock records.",
                    "Explore, edite, retire y agrupe registros de inventario.",
                ),
                "steps": [
                    _text("Use Products to find SKUs, counts, reorder levels, and locations.", "Use Productos para encontrar SKUs, cantidades, niveles de pedido y ubicaciones."),
                    _text("Use Customers to group programs and fulfillment inventory.", "Use Clientes para agrupar programas e inventario de cumplimiento."),
                    _text("Managers can create and retire records; viewers can inspect them.", "Los gerentes pueden crear y retirar registros; los lectores pueden revisarlos."),
                ],
            },
            {
                "slug": "counts-tags-imports",
                "title": _text("Counts, shelf tags, and CSV import", "Conteos, etiquetas e importar CSV"),
                "summary": _text(
                    "Keep physical inventory aligned with Retriever.",
                    "Mantenga el inventario físico alineado con Retriever.",
                ),
                "steps": [
                    _text("Use Physical Counts to verify actual shelf quantity.", "Use Conteos físicos para verificar cantidades reales."),
                    _text("Print Shelf Tags after products and zones are correct.", "Imprima etiquetas después de confirmar productos y zonas."),
                    _text("Use CSV import for bulk product setup, then review the preview before saving.", "Use importar CSV para cargas masivas y revise la vista previa antes de guardar."),
                ],
            },
        ],
    },
]


def user_can_view_module(user: CurrentUser, module: HelpModule) -> bool:
    permission = str(module.get("permission") or "")
    if user.status != "active":
        return False
    if permission == "active":
        return True
    if permission == "fetch":
        return user.can_open_fetch_shell()
    if permission == "wiki":
        return user.can_open_wiki()
    if permission == "prepress":
        return user.can_open_prepress()
    if permission == "dsf":
        return user.can_open_dsf()
    if permission == "inventory":
        return user.can_open_inventory()
    if permission == "admin":
        return user.has_module("admin")
    return False


def topic_visible_to_user(user: CurrentUser, topic: HelpTopic) -> bool:
    return not topic.get("admin_only") or user.is_admin or user.has_module("admin")


def visible_topics(user: CurrentUser, module: HelpModule) -> list[HelpTopic]:
    return [topic for topic in module["topics"] if topic_visible_to_user(user, topic)]


def visible_modules(user: CurrentUser) -> list[HelpModule]:
    modules: list[HelpModule] = []
    for module in HELP_MODULES:
        if user_can_view_module(user, module) and visible_topics(user, module):
            modules.append(module)
    return modules


def get_module(slug: str, modules: Optional[Iterable[HelpModule]] = None) -> Optional[HelpModule]:
    for module in modules or HELP_MODULES:
        if module["slug"] == slug:
            return module
    return None


def get_topic(module: HelpModule, slug: str) -> Optional[HelpTopic]:
    for topic in module["topics"]:
        if topic["slug"] == slug:
            return topic
    return None
