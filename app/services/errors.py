"""Falhas de domínio estáveis, sem dados de clientes nem detalhes técnicos."""


class ServiceError(RuntimeError):
    code = "service_error"

    def __init__(self) -> None:
        super().__init__(self.code)


class ProductNotFound(ServiceError):
    code = "not_found"


class AmbiguousProduct(ServiceError):
    code = "ambiguous"


class ProductUnavailable(ServiceError):
    code = "unavailable"


class InvalidInstallments(ServiceError):
    code = "invalid_installments"


class OrderAccessDenied(ServiceError):
    code = "forbidden"


class ServiceUnavailable(ServiceError):
    code = "service_unavailable"
