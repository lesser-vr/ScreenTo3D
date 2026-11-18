#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <d3d11_1.h>
#include <dxgi1_2.h>
#include <wrl/client.h>

#include <chrono>
#include <cstdio>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;
using namespace std::chrono_literals;

static void check(HRESULT result, const char* stage) {
    if (FAILED(result)) {
        char detail[128]{};
        std::snprintf(detail, sizeof(detail), "%s HRESULT 0x%08lX", stage,
                      static_cast<unsigned long>(result));
        throw std::runtime_error(detail);
    }
}

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wp, LPARAM lp) {
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(window, message, wp, lp);
}

class Source {
public:
    explicit Source(HWND window) : window_(window) {
        ComPtr<ID3D11DeviceContext> context;
        check(D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr,
            D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0, D3D11_SDK_VERSION,
            &device_, nullptr, &context), "D3D11CreateDevice");
        check(context.As(&context_), "Query ID3D11DeviceContext1");
        ComPtr<IDXGIDevice> dxgi;
        ComPtr<IDXGIAdapter> adapter;
        ComPtr<IDXGIFactory2> factory;
        check(device_.As(&dxgi), "Query IDXGIDevice");
        check(dxgi->GetAdapter(&adapter), "GetAdapter");
        check(adapter->GetParent(IID_PPV_ARGS(&factory)), "GetFactory");
        DXGI_SWAP_CHAIN_DESC1 descriptor{};
        descriptor.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
        descriptor.SampleDesc.Count = 1;
        descriptor.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
        descriptor.BufferCount = 2;
        descriptor.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        check(factory->CreateSwapChainForHwnd(device_.Get(), window_, &descriptor, nullptr,
                                             nullptr, &swap_), "CreateSwapChainForHwnd");
        bind();
    }

    void resize(int width, int height) {
        if (width != width_ || height != height_) {
            RECT bounds{0, 0, width, height};
            if (!AdjustWindowRectEx(&bounds, style, FALSE, 0) ||
                !SetWindowPos(window_, nullptr, 0, 0, bounds.right-bounds.left,
                              bounds.bottom-bounds.top, SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE))
                throw std::runtime_error("Resize test window failed");
        }
        target_.Reset();
        context_->ClearState();
        context_->Flush();
        check(swap_->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, 0), "ResizeBuffers");
        bind();
        ++generation;
    }

    void present() {
        constexpr float background[]{.06f, .10f, .16f, 1.f};
        constexpr float foreground[]{.85f, .58f, .12f, 1.f};
        constexpr float stripe[]{.10f, .50f, .66f, 1.f};
        const auto x = LONG((frame * 7) % (width_ - width_/4));
        const D3D11_RECT moving{x, height_/4, x+width_/4, 3*height_/4};
        const auto marker = LONG(frame % 8) * (width_/8);
        const D3D11_RECT counter{marker, 0, marker+width_/8, height_/10};
        context_->ClearRenderTargetView(target_.Get(), background);
        context_->ClearView(target_.Get(), foreground, &moving, 1);
        context_->ClearView(target_.Get(), stripe, &counter, 1);
        check(swap_->Present(0, 0), "Present");
        const auto now = Clock::now();
        last_gap_us_ = frame ? std::chrono::duration_cast<std::chrono::microseconds>(
            now - last_present_).count() : 0;
        last_present_ = now;
        ++frame;
    }

    void status() const {
        std::cout << "ok " << frame << ' ' << width_ << ' ' << height_ << ' '
                  << generation << ' ' << last_gap_us_ << std::endl;
    }

    static constexpr DWORD style = WS_POPUP;
    unsigned long long frame{};
    unsigned generation{1};

private:
    void bind() {
        RECT area{};
        if (!GetClientRect(window_, &area))
            throw std::runtime_error("GetClientRect failed");
        width_ = area.right;
        height_ = area.bottom;
        ComPtr<ID3D11Texture2D> back_buffer;
        check(swap_->GetBuffer(0, IID_PPV_ARGS(&back_buffer)), "GetBuffer");
        check(device_->CreateRenderTargetView(back_buffer.Get(), nullptr, &target_), "CreateRTV");
    }
    HWND window_;
    int width_{}, height_{};
    Clock::time_point last_present_{};
    long long last_gap_us_{};
    ComPtr<ID3D11Device> device_;
    ComPtr<ID3D11DeviceContext1> context_;
    ComPtr<IDXGISwapChain1> swap_;
    ComPtr<ID3D11RenderTargetView> target_;
};

int main() {
    try {
        if (!SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2))
            throw std::runtime_error("Cannot set test window DPI awareness");
        const HINSTANCE instance = GetModuleHandleW(nullptr);
        WNDCLASSW cls{};
        cls.lpfnWndProc = window_proc;
        cls.hInstance = instance;
        cls.lpszClassName = L"ScreenTo3D.D3D11TestSource";
        if (!RegisterClassW(&cls))
            throw std::runtime_error("RegisterClass failed");
        HWND window = CreateWindowExW(0, cls.lpszClassName, L"ScreenTo3D D3D11 test input",
                                     Source::style, 32, 32, 640, 360, nullptr, nullptr, instance, nullptr);
        if (!window)
            throw std::runtime_error("CreateWindow failed");

        Source source(window);
        source.resize(640, 360);
        ShowWindow(window, SW_SHOWNOACTIVATE);
        source.present();
        std::cout << "ready " << reinterpret_cast<uintptr_t>(window) << std::endl;
        auto next = Clock::now();
        auto resume = Clock::time_point::min();
        bool hold_pending = false;
        const HANDLE input = GetStdHandle(STD_INPUT_HANDLE);
        constexpr auto period = std::chrono::nanoseconds(1'000'000'000 / 60);
        for (;;) {
            MSG message{};
            while (PeekMessageW(&message, nullptr, 0, 0, PM_REMOVE)) {
                if (message.message == WM_QUIT)
                    return 0;
                TranslateMessage(&message);
                DispatchMessageW(&message);
            }
            DWORD bytes{};
            if (!PeekNamedPipe(input, nullptr, 0, nullptr, &bytes, nullptr))
                return 0;  // The parent closed its input pipe.
            if (bytes) {
                std::string line, command;
                if (!std::getline(std::cin, line))
                    return 0;
                std::istringstream arguments(line);
                arguments >> command;
                if (command == "close") {
                    DestroyWindow(window);
                    return 0;
                }
                if (command == "hold") {
                    int ms{};
                    if (!(arguments >> ms) || ms < 1 || ms > 2000 || hold_pending)
                        throw std::runtime_error("Invalid hold command");
                    resume = Clock::now() + std::chrono::milliseconds(ms);
                    hold_pending = true;
                } else if (command == "resize") {
                    int width{}, height{};
                    if (!(arguments >> width >> height) || width < 320 || width > 1920 ||
                        height < 180 || height > 1080)
                        throw std::runtime_error("Invalid resize command");
                    source.resize(width, height);
                    source.status();
                } else if (command == "status") {
                    source.status();
                } else {
                    throw std::runtime_error("Unknown test source command");
                }
            }
            const auto now = Clock::now();
            if (now >= resume && now >= next) {
                source.present();
                next += period;
                if (next < now)
                    next = now + period;
                if (hold_pending) {
                    source.status();
                    hold_pending = false;
                }
            }
            // Process window and pipe messages throughout a source hold.
            MsgWaitForMultipleObjectsEx(0, nullptr, 1, QS_ALLINPUT, MWMO_INPUTAVAILABLE);
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << std::endl;
        return 1;
    }
}
