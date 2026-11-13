#include "test_support.h"

#include "screento3d/foundation/capabilities.h"

#include <string>

SCREENTO3D_TEST("availability strings are stable") {
    screento3d::test::require(screento3d::to_string(screento3d::Availability::available) ==
                                "available",
                            "available spelling changed");
    screento3d::test::require(screento3d::to_string(screento3d::Availability::unavailable) ==
                                "unavailable",
                            "unavailable spelling changed");
    screento3d::test::require(screento3d::to_string(screento3d::Availability::unknown) == "unknown",
                            "unknown spelling changed");
}

SCREENTO3D_TEST("capability JSON escapes diagnostics") {
    screento3d::SystemCapabilities capabilities;
    capabilities.platform = "test";
    capabilities.cuda_driver = {screento3d::Availability::unavailable, "",
                                "quoted \"value\"\nnext"};
    capabilities.gpus.push_back({0, "GPU \\ sample", 1, 2, 4096});
    const auto json = screento3d::to_json(capabilities, false);
    screento3d::test::require(
        json.find("quoted \\\"value\\\"\\nnext") != std::string::npos,
        "diagnostic was not escaped");
    screento3d::test::require(json.find("GPU \\\\ sample") != std::string::npos,
                            "GPU name was not escaped");
}
