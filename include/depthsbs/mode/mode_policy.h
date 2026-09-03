#pragma once

#include <optional>
#include <string>
#include <string_view>

namespace depthsbs {

enum class ProcessingMode {
    performance,
    balanced,
    video_quality,
    offline_quality,
};

enum class TemporalPolicy {
    full_rate,
    online_stateful,
    model_native_or_propagated,
};

struct ProcessingPlan {
    ProcessingMode mode;
    std::string depth_backend;
    std::string precision;
    TemporalPolicy temporal_policy;
    int target_fps_min;
    int target_fps_max;
    bool realtime_required;
    bool experimental;
};

[[nodiscard]] std::optional<ProcessingMode> parse_processing_mode(std::string_view value);
[[nodiscard]] ProcessingPlan resolve_processing_plan(ProcessingMode mode);
[[nodiscard]] std::string_view to_string(ProcessingMode mode) noexcept;
[[nodiscard]] std::string_view to_string(TemporalPolicy policy) noexcept;
[[nodiscard]] std::string to_json(const ProcessingPlan& plan, bool pretty);

}  // namespace depthsbs
