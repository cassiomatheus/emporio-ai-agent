"""Excertos de políticas e dados públicos, sem expor o documento integral."""

from app.retrieval.models import PolicySearch
from app.services.errors import ServiceUnavailable
from app.services.policy_service import PolicyService, StoreInfo
from app.tools.common import NoEvidence, run_tool
from app.tools.schemas import PolicyMatchesData, PolicySearchInput, StoreInfoInput, ToolResponse


class PolicyTools:
    def __init__(self, service: PolicyService | None) -> None:
        self.service = service

    def search_store_policies(self, arguments: object) -> ToolResponse[PolicyMatchesData]:
        def operation(params: PolicySearchInput) -> PolicyMatchesData:
            if self.service is None:
                raise ServiceUnavailable()
            response = self.service.search(PolicySearch(**params.model_dump()))
            if response.status == "no_evidence" or not response.hits:
                raise NoEvidence()
            if len(response.hits) > params.top_k:
                raise ServiceUnavailable()
            return PolicyMatchesData(**response.model_dump(warnings="error"))

        return run_tool(arguments, PolicySearchInput, PolicyMatchesData, operation)

    def get_store_info(self, arguments: object) -> ToolResponse[StoreInfo]:
        def operation(params: StoreInfoInput) -> StoreInfo:
            if self.service is None:
                raise ServiceUnavailable()
            response = self.service.get_store_info(params.subject)
            if not response.entries:
                raise NoEvidence()
            return response

        return run_tool(arguments, StoreInfoInput, StoreInfo, operation)
