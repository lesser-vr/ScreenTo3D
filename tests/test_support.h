#pragma once

#include <functional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace screento3d::test {

using TestFunction = std::function<void()>;
using TestCase = std::pair<std::string, TestFunction>;

std::vector<TestCase>& registry();

struct Registrar {
    Registrar(std::string name, TestFunction function);
};

inline void require(const bool condition, const std::string& message) {
    if (!condition) throw std::runtime_error(message);
}

}  // namespace screento3d::test

#define SCREENTO3D_TEST_CONCAT_INNER(a, b) a##b
#define SCREENTO3D_TEST_CONCAT(a, b) SCREENTO3D_TEST_CONCAT_INNER(a, b)
#define SCREENTO3D_TEST(name)                                                        \
    static void SCREENTO3D_TEST_CONCAT(test_function_, __LINE__)();                  \
    static ::screento3d::test::Registrar SCREENTO3D_TEST_CONCAT(test_registrar_,       \
                                                             __LINE__)(             \
        name, SCREENTO3D_TEST_CONCAT(test_function_, __LINE__));                     \
    static void SCREENTO3D_TEST_CONCAT(test_function_, __LINE__)()
