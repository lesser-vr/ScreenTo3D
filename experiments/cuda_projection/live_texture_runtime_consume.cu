// Test-only native publication consumer. Acquires key 1 and returns key 0
// without copying pixels, matching the synchronization portion of the GUI.
#define SCREENTO3D_TEXTURE_TIMING
#include "live_texture_pool.cu"

extern "C" __declspec(dllexport) int live_pool_consume(void* value,int index) {
    if(!value){projection_texture_error="Missing pool";return 0;}
    auto* pool=static_cast<OwnedTexturePool*>(value);
    return live_texture_release(pool->texture.get(),index);
}
