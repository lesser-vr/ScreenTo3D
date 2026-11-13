#include "screento3d/mode/mode_policy.h"

#include <algorithm>
#include <cctype>
#include <sstream>
#include <stdexcept>

namespace screento3d {
namespace {

std::string normalize(std::string_view value) {
    std::string result;
    result.reserve(value.size());
    for (const unsigned char character : value) {
        if (character == '-' || character == ' ') {
            result.push_back('_');
        } else {
            result.push_back(static_cast<char>(std::tolower(character)));
        }
    }
    return result;
}

}  // namespace

std::optional<ProcessingMode> parse_processing_mode(const std::string_view value) {
    const auto normalized = normalize(value);
    if (normalized == "performance") return ProcessingMode::performance;
    if (normalized == "balanced") return ProcessingMode::balanced;
    if (normalized == "video_quality") return ProcessingMode::video_quality;
    if (normalized == "offline_quality") return ProcessingMode::offline_quality;
    return std::nullopt;
}

ProcessingPlan resolve_processing_plan(const ProcessingMode mode) {
    switch (mode) {
        case ProcessingMode::performance:
            return {mode, "da2-small-tensorrt", "fp16", TemporalPolicy::full_rate,
                    60, 120, true, true};
        case ProcessingMode::balanced:
            return {mode, "da2-base-tensorrt", "fp16", TemporalPolicy::full_rate,
                    60, 60, true, true};
        case ProcessingMode::video_quality:
            return {mode, "ovda-small-tensorrt", "fp16",
                    TemporalPolicy::online_stateful, 30, 60, true, true};
        case ProcessingMode::offline_quality:
            return {mode, "unresolved-quality-backend", "backend-defined",
                    TemporalPolicy::model_native_or_propagated, 0, 0, false, true};
    }
    throw std::invalid_argument("unknown processing mode");
}

std::string_view to_string(const ProcessingMode mode) noexcept {
    switch (mode) {
        case ProcessingMode::performance: return "performance";
        case ProcessingMode::balanced: return "balanced";
        case ProcessingMode::video_quality: return "video_quality";
        case ProcessingMode::offline_quality: return "offline_quality";
    }
    return "unknown";
}

std::string_view to_string(const TemporalPolicy policy) noexcept {
    switch (policy) {
        case TemporalPolicy::full_rate: return "full_rate";
        case TemporalPolicy::online_stateful: return "online_stateful";
        case TemporalPolicy::model_native_or_propagated:
            return "model_native_or_propagated";
    }
    return "unknown";
}

std::string to_json(const ProcessingPlan& plan, const bool pretty) {
    const auto newline = pretty ? "\n" : "";
    const auto separator = pretty ? " " : "";
    const auto indent = pretty ? "  " : "";
    std::ostringstream output;
    output << '{' << newline
           << indent << "\"mode\":" << separator << '"' << to_string(plan.mode) << "\"," << newline
           << indent << "\"depth_backend\":" << separator << '"' << plan.depth_backend << "\"," << newline
           << indent << "\"precision\":" << separator << '"' << plan.precision << "\"," << newline
           << indent << "\"temporal_policy\":" << separator << '"'
           << to_string(plan.temporal_policy) << "\"," << newline
           << indent << "\"target_fps_min\":" << separator << plan.target_fps_min << ',' << newline
           << indent << "\"target_fps_max\":" << separator << plan.target_fps_max << ',' << newline
           << indent << "\"realtime_required\":" << separator
           << (plan.realtime_required ? "true" : "false") << ',' << newline
           << indent << "\"experimental\":" << separator
           << (plan.experimental ? "true" : "false") << newline
           << '}' << newline;
    return output.str();
}

}  // namespace screento3d
