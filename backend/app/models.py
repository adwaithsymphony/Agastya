"""Import every ORM model so metadata is complete (used by Alembic and tests)."""
from app.core.db import Base  # noqa: F401
from app.modules.audit.models import AuditEvent, IdempotencyRecord  # noqa: F401
from app.modules.farms.models import CropCycle, CropReference, Farm, Field, GrowthStageRecord  # noqa: F401
from app.modules.identity.models import Organization, User  # noqa: F401
from app.modules.monitoring.models import (  # noqa: F401
    CropObservation,
    HumanReview,
    ModelPrediction,
    ModelRegistryEntry,
    UploadedImage,
)
from app.modules.notifications.models import Notification  # noqa: F401
from app.modules.pesticide.models import (  # noqa: F401
    HarvestAssessment,
    PesticideApplication,
    PesticideProduct,
    ProductLabel,
)
from app.modules.pollination.models import (  # noqa: F401
    BookingEvent,
    PollinationBooking,
    ProviderAvailability,
    ProviderCrop,
    ProviderProfile,
    ProviderServiceArea,
)
from app.modules.produce.models import (  # noqa: F401
    BatchAssignment,
    BuyerDemand,
    BuyerMatch,
    BuyerProfile,
    ProduceBatch,
    RerouteRun,
    Shipment,
    ShipmentEvent,
)

from app.modules.plant_intelligence.models import CropCareGuidance, PlantActivity, PlantObservation  # noqa: F401
