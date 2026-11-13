#include "test_support.h"

#include "screento3d/mode/mode_policy.h"

#include <array>
#include <string>

SCREENTO3D_TEST("all documented mode spellings parse") {
    using screento3d::ProcessingMode;
    const std::array cases{
        std::pair{"performance", ProcessingMode::performance},
        std::pair{"Balanced", ProcessingMode::balanced},
        std::pair{"video-quality", ProcessingMode::video_quality},
        std::pair{"Offline Quality", ProcessingMode::offline_quality},
    };
    for (const auto& [input, expected] : cases) {
        const auto parsed = screento3d::parse_processing_mode(input);
        screento3d::test::require(parsed.has_value(), "mode should parse: " + std::string(input));
        screento3d::test::require(*parsed == expected, "mode parsed incorrectly");
    }
}

SCREENTO3D_TEST("unknown modes are rejected") {
    screento3d::test::require(!screento3d::parse_processing_mode("ultra").has_value(),
                            "unknown mode must not parse");
}

SCREENTO3D_TEST("mode policies match the product specification") {
    const auto performance =
        screento3d::resolve_processing_plan(screento3d::ProcessingMode::performance);
    screento3d::test::require(performance.depth_backend == "da2-small-tensorrt",
                            "performance backend mismatch");
    screento3d::test::require(performance.target_fps_min == 60 &&
                                performance.target_fps_max == 120,
                            "performance target mismatch");

    const auto balanced =
        screento3d::resolve_processing_plan(screento3d::ProcessingMode::balanced);
    screento3d::test::require(balanced.depth_backend == "da2-base-tensorrt",
                            "balanced backend mismatch");

    const auto video_quality =
        screento3d::resolve_processing_plan(screento3d::ProcessingMode::video_quality);
    screento3d::test::require(
        video_quality.temporal_policy == screento3d::TemporalPolicy::online_stateful,
        "video quality must be stateful");

    const auto offline =
        screento3d::resolve_processing_plan(screento3d::ProcessingMode::offline_quality);
    screento3d::test::require(!offline.realtime_required,
                            "offline quality must not promise realtime");
}

SCREENTO3D_TEST("processing plan JSON is machine-readable in shape") {
    const auto plan = screento3d::resolve_processing_plan(screento3d::ProcessingMode::balanced);
    const auto json = screento3d::to_json(plan, false);
    screento3d::test::require(json.find("\"mode\":\"balanced\"") != std::string::npos,
                            "mode missing from JSON");
    screento3d::test::require(json.find("\"experimental\":true") != std::string::npos,
                            "experimental flag missing from JSON");
}
