#include "test_support.h"

#include "depthsbs/foundation/capabilities.h"

#include <string>

DEPTHSBS_TEST("availability strings are stable") {
    depthsbs::test::require(depthsbs::to_string(depthsbs::Availability::available) ==
                                "available",
                            "available spelling changed");
    depthsbs::test::require(depthsbs::to_string(depthsbs::Availability::unavailable) ==
                                "unavailable",
                            "unavailable spelling changed");
    depthsbs::test::require(depthsbs::to_string(depthsbs::Availability::unknown) == "unknown",
                            "unknown spelling changed");
}

DEPTHSBS_TEST("capability JSON escapes diagnostics") {
    depthsbs::SystemCapabilities capabilities;
    capabilities.platform = "test";
    capabilities.cuda_driver = {depthsbs::Availability::unavailable, "",
                                "quoted \"value\"\nnext"};
    capabilities.gpus.push_back({0, "GPU \\ sample", 1, 2, 4096});
    const auto json = depthsbs::to_json(capabilities, false);
    depthsbs::test::require(
        json.find("quoted \\\"value\\\"\\nnext") != std::string::npos,
        "diagnostic was not escaped");
    depthsbs::test::require(json.find("GPU \\\\ sample") != std::string::npos,
                            "GPU name was not escaped");
}
