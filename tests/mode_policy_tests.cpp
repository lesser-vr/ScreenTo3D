#include "test_support.h"

#include "depthsbs/mode/mode_policy.h"

#include <array>
#include <string>

DEPTHSBS_TEST("all documented mode spellings parse") {
    using depthsbs::ProcessingMode;
    const std::array cases{
        std::pair{"performance", ProcessingMode::performance},
        std::pair{"Balanced", ProcessingMode::balanced},
        std::pair{"video-quality", ProcessingMode::video_quality},
        std::pair{"Offline Quality", ProcessingMode::offline_quality},
    };
    for (const auto& [input, expected] : cases) {
        const auto parsed = depthsbs::parse_processing_mode(input);
        depthsbs::test::require(parsed.has_value(), "mode should parse: " + std::string(input));
        depthsbs::test::require(*parsed == expected, "mode parsed incorrectly");
    }
}

DEPTHSBS_TEST("unknown modes are rejected") {
    depthsbs::test::require(!depthsbs::parse_processing_mode("ultra").has_value(),
                            "unknown mode must not parse");
}

DEPTHSBS_TEST("mode policies match the product specification") {
    const auto performance =
        depthsbs::resolve_processing_plan(depthsbs::ProcessingMode::performance);
    depthsbs::test::require(performance.depth_backend == "da2-small-tensorrt",
                            "performance backend mismatch");
    depthsbs::test::require(performance.target_fps_min == 60 &&
                                performance.target_fps_max == 120,
                            "performance target mismatch");

    const auto balanced =
        depthsbs::resolve_processing_plan(depthsbs::ProcessingMode::balanced);
    depthsbs::test::require(balanced.depth_backend == "da2-base-tensorrt",
                            "balanced backend mismatch");

    const auto video_quality =
        depthsbs::resolve_processing_plan(depthsbs::ProcessingMode::video_quality);
    depthsbs::test::require(
        video_quality.temporal_policy == depthsbs::TemporalPolicy::online_stateful,
        "video quality must be stateful");

    const auto offline =
        depthsbs::resolve_processing_plan(depthsbs::ProcessingMode::offline_quality);
    depthsbs::test::require(!offline.realtime_required,
                            "offline quality must not promise realtime");
}

DEPTHSBS_TEST("processing plan JSON is machine-readable in shape") {
    const auto plan = depthsbs::resolve_processing_plan(depthsbs::ProcessingMode::balanced);
    const auto json = depthsbs::to_json(plan, false);
    depthsbs::test::require(json.find("\"mode\":\"balanced\"") != std::string::npos,
                            "mode missing from JSON");
    depthsbs::test::require(json.find("\"experimental\":true") != std::string::npos,
                            "experimental flag missing from JSON");
}
